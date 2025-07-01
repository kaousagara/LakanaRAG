from __future__ import annotations
from functools import partial

import asyncio
import json
import re
import os
from typing import Any, AsyncIterator
from collections import Counter, defaultdict
from itertools import combinations

from .utils import (
    logger,
    clean_str,
    compute_mdhash_id,
    Tokenizer,
    is_float_regex,
    normalize_extracted_info,
    standardize_entity_name,
    pack_user_ass_to_openai_messages,
    split_string_by_multi_markers,
    truncate_list_by_token_size,
    process_combine_contexts,
    compute_args_hash,
    handle_cache,
    save_to_cache,
    CacheData,
    get_conversation_turns,
    use_llm_func_with_cache,
)
from .base import (
    BaseGraphStorage,
    BaseKVStorage,
    BaseVectorStorage,
    TextChunkSchema,
    QueryParam,
)
from .prompt import GRAPH_FIELD_SEP, PROMPTS
from .constants import DEFAULT_ENTITY_LINK_BASE_URL, MAX_VECTOR_CONTENT_LENGTH
from .user_profile import personalize_query
import time
from dotenv import load_dotenv

# use the .env that is inside the current folder
# allows to use different .env file for each lightrag instance
# the OS environment variables take precedence over the .env file
load_dotenv(dotenv_path=".env", override=False)

# Limit concurrent Redis fetches to avoid exhausting connection pool
CHUNK_FETCH_MAX_CONCURRENCY = 20


def chunking_by_token_size(
    tokenizer: Tokenizer,
    content: str,
    split_by_character: str | None = None,
    split_by_character_only: bool = False,
    overlap_token_size: int = 128,
    max_token_size: int = 1024,
) -> list[dict[str, Any]]:
    tokens = tokenizer.encode(content)
    results: list[dict[str, Any]] = []
    if split_by_character:
        raw_chunks = content.split(split_by_character)
        new_chunks = []
        if split_by_character_only:
            for chunk in raw_chunks:
                _tokens = tokenizer.encode(chunk)
                new_chunks.append((len(_tokens), chunk))
        else:
            for chunk in raw_chunks:
                _tokens = tokenizer.encode(chunk)
                if len(_tokens) > max_token_size:
                    for start in range(
                        0, len(_tokens), max_token_size - overlap_token_size
                    ):
                        chunk_content = tokenizer.decode(
                            _tokens[start : start + max_token_size]
                        )
                        new_chunks.append(
                            (min(max_token_size, len(_tokens) - start), chunk_content)
                        )
                else:
                    new_chunks.append((len(_tokens), chunk))
        for index, (_len, chunk) in enumerate(new_chunks):
            results.append(
                {
                    "tokens": _len,
                    "content": chunk.strip(),
                    "chunk_order_index": index,
                }
            )
    else:
        for index, start in enumerate(
            range(0, len(tokens), max_token_size - overlap_token_size)
        ):
            chunk_content = tokenizer.decode(tokens[start : start + max_token_size])
            results.append(
                {
                    "tokens": min(max_token_size, len(tokens) - start),
                    "content": chunk_content.strip(),
                    "chunk_order_index": index,
                }
            )
    return results


def _hyperlink_name(name: str, entity_type: str | None, base_url: str) -> str:
    """Return a markdown hyperlink for persons and organisations."""
    if entity_type and entity_type.lower() in {
        "personne",
        "organisation",
        "person",
        "organization",
    }:
        from urllib.parse import quote

        if not base_url.endswith("/"):
            base_url = f"{base_url}/"

        return f"[{name}]({base_url}{quote(name)})"
    return name


def _truncate_content(content: str, limit: int = MAX_VECTOR_CONTENT_LENGTH) -> str:
    """Ensure content does not exceed vector DB field limits."""
    if content and len(content) > limit:
        return content[:limit]
    return content


def _add_entity_links(
    entities: list[dict],
    relations: list[dict],
    multi_hops: list[dict],
    base_url: str,
) -> tuple[list[dict], list[dict], list[dict]]:
    """Add hyperlinks to entity names in contexts."""

    type_map = {
        e.get("entity") or e.get("entity_name"): e.get("type") or e.get("entity_type")
        for e in entities
    }

    def copy_ent(ent: dict) -> dict:
        new_ent = ent.copy()
        key = "entity" if "entity" in ent else "entity_name"
        new_ent[key] = _hyperlink_name(
            ent[key], new_ent.get("type") or new_ent.get("entity_type"), base_url
        )
        return new_ent

    new_entities = [copy_ent(e) for e in entities]

    new_relations = []
    for rel in relations:
        nr = rel.copy()
        for k in ("entity1", "entity2", "source_entity", "target_entity"):
            if k in nr:
                nr[k] = _hyperlink_name(nr[k], type_map.get(nr[k]), base_url)
        new_relations.append(nr)

    new_multi_hops = []
    for mh in multi_hops:
        nm = mh.copy()
        if "path_entities" in nm:
            nm["path_entities"] = [
                _hyperlink_name(name, type_map.get(name), base_url)
                for name in nm["path_entities"]
            ]
        new_multi_hops.append(nm)

    return new_entities, new_relations, new_multi_hops


async def _handle_entity_relation_summary(
    entity_or_relation_name: str,
    description: str,
    global_config: dict,
    pipeline_status: dict = None,
    pipeline_status_lock=None,
    llm_response_cache: BaseKVStorage | None = None,
) -> str:
    """Handle entity relation summary
    For each entity or relation, input is the combined description of already existing description and new description.
    If too long, use LLM to summarize.
    """
    use_llm_func: callable = global_config["llm_model_func"]
    # Apply higher priority (8) to entity/relation summary tasks
    use_llm_func = partial(use_llm_func, _priority=8)

    tokenizer: Tokenizer = global_config["tokenizer"]
    llm_max_tokens = global_config["llm_model_max_token_size"]
    summary_max_tokens = global_config["summary_to_max_tokens"]

    language = global_config["addon_params"].get(
        "language", PROMPTS["DEFAULT_LANGUAGE"]
    )

    tokens = tokenizer.encode(description)

    ### summarize is not determined here anymore (It's determined by num_fragment now)
    # if len(tokens) < summary_max_tokens:  # No need for summary
    #     return description

    prompt_template = PROMPTS["summarize_entity_descriptions"]
    use_description = tokenizer.decode(tokens[:llm_max_tokens])
    context_base = dict(
        entity_name=entity_or_relation_name,
        description_list=use_description.split(GRAPH_FIELD_SEP),
        language=language,
    )
    use_prompt = prompt_template.format(**context_base)
    logger.debug(f"Trigger summary: {entity_or_relation_name}")

    # Use LLM function with cache (higher priority for summary generation)
    summary = await use_llm_func_with_cache(
        use_prompt,
        use_llm_func,
        llm_response_cache=llm_response_cache,
        max_tokens=summary_max_tokens,
        cache_type="extract",
    )
    return summary


async def _handle_single_entity_extraction(
    record_attributes: list[str],
    chunk_key: str,
    file_path: str = "unknown_source",
):
    if len(record_attributes) < 6 or '"entity"' not in record_attributes[0]:
        return None

    # Clean and validate entity name
    entity_name = clean_str(record_attributes[1]).strip()
    if not entity_name:
        logger.warning(
            f"Entity extraction error: empty entity name in: {record_attributes}"
        )
        return None

    # Normalize entity name
    entity_name = normalize_extracted_info(entity_name, is_entity=True)
    entity_name = standardize_entity_name(entity_name)

    # Clean and validate entity type
    entity_type = clean_str(record_attributes[2]).strip('"')
    if not entity_type.strip() or entity_type.startswith('("'):
        logger.warning(
            f"Entity extraction error: invalid entity type in: {record_attributes}"
        )
        return None

    # Clean and validate description
    entity_description = clean_str(record_attributes[3])
    entity_description = normalize_extracted_info(entity_description)

    additional_properties = normalize_extracted_info(clean_str(record_attributes[4]))

    entity_community = (
        normalize_extracted_info(clean_str(record_attributes[5])) or "inconnue"
    )

    if not entity_description.strip():
        logger.warning(
            f"Entity extraction error: empty description for entity '{entity_name}' of type '{entity_type}'"
        )
        return None

    return dict(
        entity_name=entity_name,
        entity_type=entity_type,
        description=entity_description,
        additional_properties=additional_properties,
        entity_community=entity_community,
        source_id=chunk_key,
        file_path=file_path,
    )


async def _handle_single_relationship_extraction(
    record_attributes: list[str],
    chunk_key: str,
    file_path: str = "unknown_source",
):
    if len(record_attributes) < 5 or '"relationship"' not in record_attributes[0]:
        return None
    # add this record as edge
    source = clean_str(record_attributes[1])
    target = clean_str(record_attributes[2])

    # Normalize source and target entity names
    source = standardize_entity_name(normalize_extracted_info(source, is_entity=True))
    target = standardize_entity_name(normalize_extracted_info(target, is_entity=True))
    if source == target:
        logger.debug(
            f"Relationship source and target are the same in: {record_attributes}"
        )
        return None

    edge_description = clean_str(record_attributes[3])
    edge_description = normalize_extracted_info(edge_description)

    edge_keywords = normalize_extracted_info(
        clean_str(record_attributes[4]), is_entity=True
    )
    edge_keywords = edge_keywords.replace("，", ",")

    edge_source_id = chunk_key
    weight = (
        float(record_attributes[-1].strip('"').strip("'"))
        if is_float_regex(record_attributes[-1].strip('"').strip("'"))
        else 1.0
    )
    return dict(
        src_id=source,
        tgt_id=target,
        weight=weight,
        description=edge_description,
        keywords=edge_keywords,
        source_id=edge_source_id,
        file_path=file_path,
    )


async def _handle_single_association_extraction(
    record_attributes: list[str],
    chunk_key: str,
    file_path: str = "unknown_source",
):
    if len(record_attributes) < 7 or '"Association"' not in record_attributes[0]:
        return None

    entities = [
        standardize_entity_name(normalize_extracted_info(e, is_entity=True))
        for e in record_attributes[1:-4]
    ]
    description = normalize_extracted_info(clean_str(record_attributes[-4]))
    generalization = normalize_extracted_info(clean_str(record_attributes[-3]))
    keywords = normalize_extracted_info(clean_str(record_attributes[-2]))
    strength = (
        float(record_attributes[-1].strip('"').strip("'"))
        if is_float_regex(record_attributes[-1].strip('"').strip("'"))
        else 1.0
    )

    return dict(
        entities=entities,
        description=description,
        generalization=generalization,
        keywords=keywords,
        strength=strength,
        source_id=chunk_key,
        file_path=file_path,
    )


async def _handle_single_multi_hop_extraction(
    record_attributes: list[str],
    chunk_key: str,
    file_path: str = "unknown_source",
):
    """Parse a multi_hop record into a dictionary."""
    if len(record_attributes) < 5 or '"multi_hop"' not in record_attributes[0]:
        return None

    entities_raw = record_attributes[1]
    # Remove brackets and split by comma
    entities = [
        standardize_entity_name(normalize_extracted_info(e.strip(), is_entity=True))
        for e in entities_raw.strip("[]").split(",")
        if e.strip()
    ]
    path_description = normalize_extracted_info(clean_str(record_attributes[2]))
    path_keywords = normalize_extracted_info(clean_str(record_attributes[3]))
    strength = (
        float(record_attributes[4].strip('"').strip("'"))
        if len(record_attributes) > 4
        and is_float_regex(record_attributes[4].strip('"').strip("'"))
        else 1.0
    )

    return dict(
        path_entities=entities,
        path_description=path_description,
        path_keywords=path_keywords,
        path_strength=strength,
        source_id=chunk_key,
        file_path=file_path,
    )


async def _handle_single_latent_relation_extraction(
    record_attributes: list[str],
    chunk_key: str,
    file_path: str = "unknown_source",
):
    """Parse a latent_relation record into an edge dict."""
    if len(record_attributes) < 6 or '"latent_relation"' not in record_attributes[0]:
        return None

    source = standardize_entity_name(
        normalize_extracted_info(clean_str(record_attributes[1]), is_entity=True)
    )
    target = standardize_entity_name(
        normalize_extracted_info(clean_str(record_attributes[2]), is_entity=True)
    )
    description = normalize_extracted_info(clean_str(record_attributes[3]))
    keywords = normalize_extracted_info(clean_str(record_attributes[4]))
    keywords = keywords.replace("，", ",")
    strength = (
        float(record_attributes[5].strip('"').strip("'"))
        if is_float_regex(record_attributes[5].strip('"').strip("'"))
        else 1.0
    )

    return dict(
        src_id=source,
        tgt_id=target,
        weight=strength,
        description=description,
        keywords=keywords,
        latent=True,
        source_id=chunk_key,
        file_path=file_path,
    )


async def _merge_nodes_then_upsert(
    entity_name: str,
    nodes_data: list[dict],
    knowledge_graph_inst: BaseGraphStorage,
    global_config: dict,
    pipeline_status: dict = None,
    pipeline_status_lock=None,
    llm_response_cache: BaseKVStorage | None = None,
):
    """Get existing nodes from knowledge graph use name,if exists, merge data, else create, then upsert."""
    entity_name = standardize_entity_name(entity_name)
    already_entity_types = []
    already_source_ids = []
    already_description = []
    already_file_paths = []
    already_additional_properties = []
    already_entity_communities = []

    already_node = await knowledge_graph_inst.get_node(entity_name)
    if already_node:
        entity_type_value = already_node.get("entity_type")
        if entity_type_value is not None:
            already_entity_types.append(entity_type_value)

        source_id_value = already_node.get("source_id")
        if source_id_value:
            already_source_ids.extend(
                split_string_by_multi_markers(source_id_value, [GRAPH_FIELD_SEP])
            )

        file_path_value = already_node.get("file_path")
        if file_path_value:
            already_file_paths.extend(
                split_string_by_multi_markers(file_path_value, [GRAPH_FIELD_SEP])
            )

        description_value = already_node.get("description")
        if description_value is not None:
            already_description.append(description_value)

        additional_prop_value = already_node.get("additional_properties")
        if additional_prop_value is not None:
            already_additional_properties.append(additional_prop_value)

        entity_comm_value = already_node.get("entity_community")
        if entity_comm_value is not None:
            already_entity_communities.append(entity_comm_value)

    entity_type = sorted(
        Counter(
            [dp.get("entity_type", "UNKNOWN") for dp in nodes_data]
            + already_entity_types
        ).items(),
        key=lambda x: x[1],
        reverse=True,
    )[0][0]
    description = GRAPH_FIELD_SEP.join(
        sorted(
            set([dp.get("description", "") for dp in nodes_data] + already_description)
        )
    )
    # Skip creation if description is empty after merging
    if not description.strip():
        logger.warning(f"Skip inserting node '{entity_name}' due to empty description")
        return None
    source_id = GRAPH_FIELD_SEP.join(
        set(
            [dp["source_id"] for dp in nodes_data if dp.get("source_id")]
            + already_source_ids
        )
    )
    file_path = GRAPH_FIELD_SEP.join(
        set(
            [dp["file_path"] for dp in nodes_data if dp.get("file_path")]
            + already_file_paths
        )
    )

    # Skip creation if node lacks chunk linkage
    if not source_id and not file_path:
        logger.warning(
            f"Skip inserting node '{entity_name}' due to missing source_id and file_path"
        )
        return None

    additional_properties = GRAPH_FIELD_SEP.join(
        sorted(
            set(
                [dp.get("additional_properties", "") for dp in nodes_data]
                + already_additional_properties
            )
        )
    )
    entity_community = GRAPH_FIELD_SEP.join(
        sorted(
            set(
                [dp.get("entity_community", "inconnue") for dp in nodes_data]
                + already_entity_communities
            )
        )
    )

    # Optionally enrich description using LLM
    if global_config.get("enable_description_enrichment"):
        use_llm_func: callable = global_config["llm_model_func"]
        use_llm_func = partial(use_llm_func, _priority=7)
        enrich_prompt = (
            f"Complète la description suivante de l'entité nommée {entity_name}. "
            f"Ajoute toute information manquante sur la date ou le lieu s'il y en a.\n"
            f"Description: {description}"
        )
        description = await use_llm_func_with_cache(
            enrich_prompt,
            use_llm_func,
            llm_response_cache=llm_response_cache,
            cache_type="enrich_desc",
        )

    if entity_type.lower() == "géographie" and global_config.get(
        "enable_geo_enrichment"
    ):
        from .utils import get_location_info

        geo_info = get_location_info(entity_name)
        if geo_info and "error" not in geo_info:
            loc_desc_parts = [
                geo_info.get("pays"),
                geo_info.get("region"),
                geo_info.get("province"),
                geo_info.get("departement"),
                geo_info.get("commune"),
            ]
            loc_desc = "/".join([p for p in loc_desc_parts if p])
            if loc_desc:
                description = f"{description} ({loc_desc}:Latitude: {geo_info.get('latitude')} | Longitude: {geo_info.get('longitude')})"
            gps_info = f"{entity_name} | Latitude: {geo_info.get('latitude')} | Longitude: {geo_info.get('longitude')}"
            if additional_properties:
                additional_properties += GRAPH_FIELD_SEP + gps_info
            else:
                additional_properties = gps_info

    force_llm_summary_on_merge = global_config["force_llm_summary_on_merge"]

    num_fragment = description.count(GRAPH_FIELD_SEP) + 1
    num_new_fragment = len(set([dp["description"] for dp in nodes_data]))

    if num_fragment > 1:
        if num_fragment >= force_llm_summary_on_merge:
            status_message = f"LLM merge N: {entity_name} | {num_new_fragment}+{num_fragment - num_new_fragment}"
            logger.info(status_message)
            if pipeline_status is not None and pipeline_status_lock is not None:
                async with pipeline_status_lock:
                    pipeline_status["latest_message"] = status_message
                    pipeline_status["history_messages"].append(status_message)
            description = await _handle_entity_relation_summary(
                entity_name,
                description,
                global_config,
                pipeline_status,
                pipeline_status_lock,
                llm_response_cache,
            )
        else:
            status_message = f"Merge N: {entity_name} | {num_new_fragment}+{num_fragment - num_new_fragment}"
            logger.info(status_message)
            if pipeline_status is not None and pipeline_status_lock is not None:
                async with pipeline_status_lock:
                    pipeline_status["latest_message"] = status_message
                    pipeline_status["history_messages"].append(status_message)

    node_data = dict(
        entity_id=entity_name,
        entity_type=entity_type,
        description=description,
        additional_properties=additional_properties,
        entity_community=entity_community,
        source_id=source_id,
        file_path=file_path,
        created_at=int(time.time()),
    )
    await knowledge_graph_inst.upsert_node(
        entity_name,
        node_data=node_data,
    )
    node_data["entity_name"] = entity_name
    return node_data


async def _merge_edges_then_upsert(
    src_id: str,
    tgt_id: str,
    edges_data: list[dict],
    knowledge_graph_inst: BaseGraphStorage,
    global_config: dict,
    pipeline_status: dict = None,
    pipeline_status_lock=None,
    llm_response_cache: BaseKVStorage | None = None,
):
    if src_id == tgt_id:
        return None
    src_id = standardize_entity_name(src_id)
    tgt_id = standardize_entity_name(tgt_id)

    already_weights = []
    already_source_ids = []
    already_description = []
    already_keywords = []
    already_file_paths = []

    if await knowledge_graph_inst.has_edge(src_id, tgt_id):
        already_edge = await knowledge_graph_inst.get_edge(src_id, tgt_id)
        # Handle the case where get_edge returns None or missing fields
        if already_edge:
            # Get weight with default 0.0 if missing
            already_weights.append(already_edge.get("weight", 0.0))

            # Get source_id with empty string default if missing or None
            if already_edge.get("source_id") is not None:
                already_source_ids.extend(
                    split_string_by_multi_markers(
                        already_edge["source_id"], [GRAPH_FIELD_SEP]
                    )
                )

            # Get file_path with empty string default if missing or None
            if already_edge.get("file_path") is not None:
                already_file_paths.extend(
                    split_string_by_multi_markers(
                        already_edge["file_path"], [GRAPH_FIELD_SEP]
                    )
                )

            # Get description with empty string default if missing or None
            if already_edge.get("description") is not None:
                already_description.append(already_edge["description"])

            # Get keywords with empty string default if missing or None
            if already_edge.get("keywords") is not None:
                already_keywords.extend(
                    split_string_by_multi_markers(
                        already_edge["keywords"], [GRAPH_FIELD_SEP]
                    )
                )

    # Process edges_data with None checks
    weight = sum([dp["weight"] for dp in edges_data] + already_weights)
    description = GRAPH_FIELD_SEP.join(
        sorted(
            set(
                [dp["description"] for dp in edges_data if dp.get("description")]
                + already_description
            )
        )
    )

    # Split all existing and new keywords into individual terms, then combine and deduplicate
    all_keywords = set()
    # Process already_keywords (which are comma-separated)
    for keyword_str in already_keywords:
        if keyword_str:  # Skip empty strings
            all_keywords.update(k.strip() for k in keyword_str.split(",") if k.strip())
    # Process new keywords from edges_data
    for edge in edges_data:
        if edge.get("keywords"):
            all_keywords.update(
                k.strip() for k in edge["keywords"].split(",") if k.strip()
            )
    # Join all unique keywords with commas
    keywords = ",".join(sorted(all_keywords))

    source_id = GRAPH_FIELD_SEP.join(
        set(
            [dp["source_id"] for dp in edges_data if dp.get("source_id")]
            + already_source_ids
        )
    )
    file_path = GRAPH_FIELD_SEP.join(
        set(
            [dp["file_path"] for dp in edges_data if dp.get("file_path")]
            + already_file_paths
        )
    )

    for need_insert_id in [src_id, tgt_id]:
        if not (await knowledge_graph_inst.has_node(need_insert_id)):
            if not source_id and not file_path:
                logger.warning(
                    f"Skip creating node '{need_insert_id}' for edge {src_id}-{tgt_id} due to missing source_id and file_path"
                )
                continue
            await knowledge_graph_inst.upsert_node(
                need_insert_id,
                node_data={
                    "entity_id": need_insert_id,
                    "source_id": source_id,
                    "description": description,
                    "entity_type": "UNKNOWN",
                    "file_path": file_path,
                    "created_at": int(time.time()),
                },
            )

    force_llm_summary_on_merge = global_config["force_llm_summary_on_merge"]

    num_fragment = description.count(GRAPH_FIELD_SEP) + 1
    num_new_fragment = len(
        set([dp["description"] for dp in edges_data if dp.get("description")])
    )

    if num_fragment > 1:
        if num_fragment >= force_llm_summary_on_merge:
            status_message = f"LLM merge E: {src_id} - {tgt_id} | {num_new_fragment}+{num_fragment - num_new_fragment}"
            logger.info(status_message)
            if pipeline_status is not None and pipeline_status_lock is not None:
                async with pipeline_status_lock:
                    pipeline_status["latest_message"] = status_message
                    pipeline_status["history_messages"].append(status_message)
            description = await _handle_entity_relation_summary(
                f"({src_id}, {tgt_id})",
                description,
                global_config,
                pipeline_status,
                pipeline_status_lock,
                llm_response_cache,
            )
        else:
            status_message = f"Merge E: {src_id} - {tgt_id} | {num_new_fragment}+{num_fragment - num_new_fragment}"
            logger.info(status_message)
            if pipeline_status is not None and pipeline_status_lock is not None:
                async with pipeline_status_lock:
                    pipeline_status["latest_message"] = status_message
                    pipeline_status["history_messages"].append(status_message)

    await knowledge_graph_inst.upsert_edge(
        src_id,
        tgt_id,
        edge_data=dict(
            weight=weight,
            description=description,
            keywords=keywords,
            source_id=source_id,
            file_path=file_path,
            created_at=int(time.time()),
        ),
    )

    edge_data = dict(
        src_id=src_id,
        tgt_id=tgt_id,
        description=description,
        keywords=keywords,
        source_id=source_id,
        file_path=file_path,
        created_at=int(time.time()),
    )

    return edge_data


async def _merge_association_then_upsert(
    assoc: dict,
    knowledge_graph_inst: BaseGraphStorage,
    global_config: dict,
    pipeline_status: dict | None = None,
    pipeline_status_lock=None,
    llm_response_cache: BaseKVStorage | None = None,
):
    entities = [standardize_entity_name(e) for e in assoc["entities"]]
    assoc_id = compute_mdhash_id("::".join(sorted(entities)), prefix="assoc-")
    description = assoc["description"] + GRAPH_FIELD_SEP + assoc["generalization"]
    if not description.strip():
        logger.warning(f"Skip association node '{assoc_id}' due to empty description")
        return None

    node_data = dict(
        entity_id=assoc_id,
        entity_type="ASSOCIATION",
        description=description,
        keywords=assoc["keywords"],
        strength=assoc["strength"],
        entities=";".join(entities),
        source_id=assoc["source_id"],
        file_path=assoc.get("file_path", "unknown_source"),
        created_at=int(time.time()),
    )

    if not node_data["source_id"] and not node_data["file_path"]:
        logger.warning(
            f"Skip association node '{assoc_id}' due to missing source_id and file_path"
        )
        return None
    await knowledge_graph_inst.upsert_node(assoc_id, node_data)

    # Link association node to its entities
    for ent in entities:
        await knowledge_graph_inst.upsert_edge(
            assoc_id,
            ent,
            edge_data=dict(
                weight=assoc["strength"],
                description=assoc["generalization"],
                keywords=assoc["keywords"],
                source_id=assoc["source_id"],
                file_path=assoc.get("file_path", "unknown_source"),
                created_at=int(time.time()),
            ),
        )

    # Also create pairwise edges between entities
    for src, tgt in combinations(entities, 2):
        await _merge_edges_then_upsert(
            src,
            tgt,
            [
                dict(
                    weight=assoc["strength"],
                    description=assoc["description"],
                    keywords=assoc["keywords"],
                    source_id=assoc["source_id"],
                    file_path=assoc.get("file_path", "unknown_source"),
                    created_at=int(time.time()),
                )
            ],
            knowledge_graph_inst,
            global_config,
            pipeline_status,
            pipeline_status_lock,
            llm_response_cache,
        )

    node_data["entity_name"] = assoc_id
    return node_data


async def _merge_multi_hop_then_upsert(
    path: dict,
    knowledge_graph_inst: BaseGraphStorage,
    global_config: dict,
    pipeline_status: dict | None = None,
    pipeline_status_lock=None,
    llm_response_cache: BaseKVStorage | None = None,
):
    """Insert a multi-hop path as a node with edges to each entity."""
    entities = [standardize_entity_name(e) for e in path["path_entities"]]
    path_id = compute_mdhash_id("->".join(entities), prefix="mh-")
    description = path["path_description"]
    if not description.strip():
        logger.warning(f"Skip multi-hop node '{path_id}' due to empty description")
        return None, []

    node_data = dict(
        entity_id=path_id,
        entity_type="MULTI_HOP",
        description=description,
        keywords=path.get("path_keywords", ""),
        strength=path.get("path_strength", 1.0),
        path="->".join(entities),
        source_id=path.get("source_id"),
        file_path=path.get("file_path", "unknown_source"),
        created_at=int(time.time()),
    )

    if not node_data["source_id"] and not node_data["file_path"]:
        logger.warning(
            f"Skip multi-hop node '{path_id}' due to missing source_id and file_path"
        )
        return None, []
    await knowledge_graph_inst.upsert_node(path_id, node_data)

    inserted_edges = []
    for ent in entities:
        edge_info = dict(
            weight=path.get("path_strength", 1.0),
            description=description,
            keywords=path.get("path_keywords", ""),
            source_id=path.get("source_id"),
            file_path=path.get("file_path", "unknown_source"),
            latent=True,
            created_at=int(time.time()),
        )
        await knowledge_graph_inst.upsert_edge(path_id, ent, edge_info)
        inserted_edges.append({"src_id": path_id, "tgt_id": ent, **edge_info})

    node_data["entity_name"] = path_id
    return node_data, inserted_edges


async def merge_nodes_and_edges(
    chunk_results: list,
    knowledge_graph_inst: BaseGraphStorage,
    entity_vdb: BaseVectorStorage,
    relationships_vdb: BaseVectorStorage,
    global_config: dict[str, str],
    pipeline_status: dict = None,
    pipeline_status_lock=None,
    llm_response_cache: BaseKVStorage | None = None,
    current_file_number: int = 0,
    total_files: int = 0,
    file_path: str = "unknown_source",
) -> None:
    """Merge nodes and edges from extraction results

    Args:
        chunk_results: List of tuples (maybe_nodes, maybe_edges,
        maybe_assocs, maybe_multi_hops) containing extracted
        entities, relationships, associations and multi-hop paths
        knowledge_graph_inst: Knowledge graph storage
        entity_vdb: Entity vector database
        relationships_vdb: Relationship vector database
        global_config: Global configuration
        pipeline_status: Pipeline status dictionary
        pipeline_status_lock: Lock for pipeline status
        llm_response_cache: LLM response cache
    """
    # Get lock manager from shared storage
    from .kg.shared_storage import get_graph_db_lock

    # Collect all nodes and edges from all chunks
    all_nodes = defaultdict(list)
    all_edges = defaultdict(list)
    all_assocs = []
    all_multi_hops = []

    for maybe_nodes, maybe_edges, maybe_assocs, maybe_mhops in chunk_results:
        # Collect nodes
        for entity_name, entities in maybe_nodes.items():
            all_nodes[entity_name].extend(entities)

        # Collect edges with sorted keys for undirected graph
        for edge_key, edges in maybe_edges.items():
            sorted_edge_key = tuple(sorted(edge_key))
            all_edges[sorted_edge_key].extend(edges)
        for assoc in maybe_assocs:
            all_assocs.append(assoc)
        for mh in maybe_mhops:
            all_multi_hops.append(mh)

    # Centralized processing of all nodes and edges
    entities_data = []
    relationships_data = []
    associations_nodes = []
    multi_hop_nodes = []

    # Merge nodes and edges
    # Use graph database lock to ensure atomic merges and updates
    graph_db_lock = get_graph_db_lock(enable_logging=False)
    async with graph_db_lock:
        async with pipeline_status_lock:
            log_message = (
                f"Merging stage {current_file_number}/{total_files}: {file_path}"
            )
            logger.info(log_message)
            pipeline_status["latest_message"] = log_message
            pipeline_status["history_messages"].append(log_message)

        # Process and update all entities at once
        for entity_name, entities in all_nodes.items():
            entity_data = await _merge_nodes_then_upsert(
                entity_name,
                entities,
                knowledge_graph_inst,
                global_config,
                pipeline_status,
                pipeline_status_lock,
                llm_response_cache,
            )
            if entity_data is not None:
                entities_data.append(entity_data)

        # Process and update all relationships at once
        for edge_key, edges in all_edges.items():
            edge_data = await _merge_edges_then_upsert(
                edge_key[0],
                edge_key[1],
                edges,
                knowledge_graph_inst,
                global_config,
                pipeline_status,
                pipeline_status_lock,
                llm_response_cache,
            )
            if edge_data is not None:
                relationships_data.append(edge_data)

        if global_config.get("enable_association", True):
            for assoc in all_assocs:
                assoc_node = await _merge_association_then_upsert(
                    assoc,
                    knowledge_graph_inst,
                    global_config,
                    pipeline_status,
                    pipeline_status_lock,
                    llm_response_cache,
                )
                if assoc_node is not None:
                    associations_nodes.append(assoc_node)

        multi_hop_edges_from_paths = []
        if global_config.get("enable_multi_hop", True):
            for mh in all_multi_hops:
                mh_node, mh_edges = await _merge_multi_hop_then_upsert(
                    mh,
                    knowledge_graph_inst,
                    global_config,
                    pipeline_status,
                    pipeline_status_lock,
                    llm_response_cache,
                )
                if mh_node is not None:
                    multi_hop_nodes.append(mh_node)
                    multi_hop_edges_from_paths.extend(mh_edges)

        # Update total counts
        total_entities_count = len(entities_data)
        total_relations_count = len(relationships_data)
        total_assoc_count = len(associations_nodes)
        total_multi_count = len(multi_hop_nodes)

        log_message = f"Updating {total_entities_count} entities  {current_file_number}/{total_files}: {file_path}"
        logger.info(log_message)
        if pipeline_status is not None:
            async with pipeline_status_lock:
                pipeline_status["latest_message"] = log_message
                pipeline_status["history_messages"].append(log_message)

        # Update vector databases with all collected data
        if entity_vdb is not None and (
            entities_data
            or (global_config.get("enable_association", True) and associations_nodes)
            or (global_config.get("enable_multi_hop", True) and multi_hop_nodes)
        ):
            all_nodes_data = entities_data
            if global_config.get("enable_association", True):
                all_nodes_data += associations_nodes
            if global_config.get("enable_multi_hop", True):
                all_nodes_data += multi_hop_nodes
            data_for_vdb = {
                compute_mdhash_id(dp["entity_name"], prefix="ent-"): {
                    "entity_name": dp["entity_name"],
                    "entity_type": dp.get("entity_type", "UNKNOWN"),
                    "content": _truncate_content(
                        f"{dp['entity_name']}\n{dp['description']}\n{dp.get('additional_properties', '')}\n{dp.get('entity_community', '')}"
                    ),
                    "source_id": dp.get("source_id"),
                    "file_path": dp.get("file_path", "unknown_source"),
                }
                for dp in all_nodes_data
            }
            await entity_vdb.upsert(data_for_vdb)

        log_message = f"Updating {total_relations_count} relations, {total_assoc_count} associations and {total_multi_count} multi-hop paths {current_file_number}/{total_files}: {file_path}"
        logger.info(log_message)
        if pipeline_status is not None:
            async with pipeline_status_lock:
                pipeline_status["latest_message"] = log_message
                pipeline_status["history_messages"].append(log_message)

        if relationships_vdb is not None and (
            relationships_data
            or (
                global_config.get("enable_multi_hop", True)
                and multi_hop_edges_from_paths
            )
        ):
            combined_edges = relationships_data
            if global_config.get("enable_multi_hop", True):
                combined_edges += multi_hop_edges_from_paths
            data_for_vdb = {
                compute_mdhash_id(e["src_id"] + e["tgt_id"], prefix="rel-"): {
                    "src_id": e["src_id"],
                    "tgt_id": e["tgt_id"],
                    "keywords": e.get("keywords", ""),
                    "content": _truncate_content(
                        f"{e['src_id']}\t{e['tgt_id']}\n{e.get('keywords', '')}\n{e.get('description', '')}"
                    ),
                    "source_id": e.get("source_id"),
                    "file_path": e.get("file_path", "unknown_source"),
                }
                for e in combined_edges
            }
            await relationships_vdb.upsert(data_for_vdb)

        if global_config.get("enable_multi_hop", True):
            # --------------------------------------------
            # Multi-hop reasoning based on inserted nodes
            # --------------------------------------------
            multi_hop_edges = []
            for ent in entities_data:
                try:
                    paths = await knowledge_graph_inst.multi_hop_paths(
                        ent["entity_name"], max_depth=3, top_k=3
                    )
                except Exception as e:
                    logger.warning(
                        f"multi_hop path search failed for {ent['entity_name']}: {e}"
                    )
                    continue

                for p in paths:
                    if len(p["path_entities"]) < 2:
                        continue
                    src = p["path_entities"][0]
                    tgt = p["path_entities"][-1]
                    edge_info = dict(
                        weight=p["path_strength"],
                        description=p["path_description"],
                        keywords=p["path_keywords"],
                        latent=True,
                        source_id=ent.get("source_id", "multi_hop"),
                        file_path=ent.get("file_path", file_path),
                        created_at=int(time.time()),
                    )
                    await knowledge_graph_inst.upsert_edge(src, tgt, edge_info)
                    multi_hop_edges.append(
                        {
                            "src_id": src,
                            "tgt_id": tgt,
                            **edge_info,
                        }
                    )

        if relationships_vdb is not None and multi_hop_edges:
            data_for_vdb = {
                compute_mdhash_id(e["src_id"] + e["tgt_id"], prefix="rel-"): {
                    "src_id": e["src_id"],
                    "tgt_id": e["tgt_id"],
                    "keywords": e["keywords"],
                    "content": _truncate_content(
                        f"{e['src_id']}\t{e['tgt_id']}\n{e['keywords']}\n{e['description']}"
                    ),
                    "source_id": e["source_id"],
                    "file_path": e.get("file_path", "unknown_source"),
                }
                for e in multi_hop_edges
            }
            await relationships_vdb.upsert(data_for_vdb)

        if global_config.get("enable_community_detection"):
            communities = await knowledge_graph_inst.detect_communities()
            update_data_vdb = {}
            for node_id, comm in communities.items():
                node = await knowledge_graph_inst.get_node(node_id)
                entity_type = node.get("entity_type", "UNKNOWN") if node else "UNKNOWN"
                await knowledge_graph_inst.upsert_node(
                    node_id,
                    {
                        "entity_id": node_id,
                        "entity_type": entity_type,
                        "entity_community": comm,
                    },
                )
                if entity_vdb is not None and node:
                    update_data_vdb[compute_mdhash_id(node_id, prefix="ent-")] = {
                        "entity_name": node_id,
                        "entity_type": entity_type,
                        "content": _truncate_content(
                            f"{node_id}\n{node.get('description', '')}\n{node.get('additional_properties', '')}\n{comm}"
                        ),
                        "source_id": node.get("source_id"),
                        "file_path": node.get("file_path", "unknown_source"),
                    }
            if entity_vdb is not None and update_data_vdb:
                await entity_vdb.upsert(update_data_vdb)


async def extract_entities(
    chunks: dict[str, TextChunkSchema],
    global_config: dict[str, str],
    pipeline_status: dict = None,
    pipeline_status_lock=None,
    llm_response_cache: BaseKVStorage | None = None,
) -> list:
    use_llm_func: callable = global_config["llm_model_func"]
    entity_extract_max_gleaning = global_config["entity_extract_max_gleaning"]

    ordered_chunks = list(chunks.items())
    # add language and example number params to prompt
    language = global_config["addon_params"].get(
        "language", PROMPTS["DEFAULT_LANGUAGE"]
    )
    entity_types = global_config["addon_params"].get(
        "entity_types", PROMPTS["DEFAULT_ENTITY_TYPES"]
    )
    example_number = global_config["addon_params"].get("example_number", None)
    if example_number and example_number < len(PROMPTS["entity_extraction_examples"]):
        examples = "\n".join(
            PROMPTS["entity_extraction_examples"][: int(example_number)]
        )
    else:
        examples = "\n".join(PROMPTS["entity_extraction_examples"])

    example_context_base = dict(
        tuple_delimiter=PROMPTS["DEFAULT_TUPLE_DELIMITER"],
        record_delimiter=PROMPTS["DEFAULT_RECORD_DELIMITER"],
        completion_delimiter=PROMPTS["DEFAULT_COMPLETION_DELIMITER"],
        entity_types=", ".join(entity_types),
        language=language,
    )
    # add example's format
    examples = examples.format(**example_context_base)

    entity_extract_prompt = PROMPTS["entity_extraction"]
    context_base = dict(
        tuple_delimiter=PROMPTS["DEFAULT_TUPLE_DELIMITER"],
        record_delimiter=PROMPTS["DEFAULT_RECORD_DELIMITER"],
        completion_delimiter=PROMPTS["DEFAULT_COMPLETION_DELIMITER"],
        entity_types=",".join(entity_types),
        examples=examples,
        language=language,
    )

    continue_prompt = PROMPTS["entity_continue_extraction"].format(**context_base)
    if_loop_prompt = PROMPTS["entity_if_loop_extraction"]

    processed_chunks = 0
    total_chunks = len(ordered_chunks)

    async def _process_extraction_result(
        result: str, chunk_key: str, file_path: str = "unknown_source"
    ):
        """Process a single extraction result (either initial or gleaning)
        Args:
            result (str): The extraction result to process
            chunk_key (str): The chunk key for source tracking
            file_path (str): The file path for citation
        Returns:
            tuple: (nodes_dict, edges_dict, associations, multi_hops)
            containing the extracted entities, relationships,
            association groups and multi-hop paths
        """
        maybe_nodes = defaultdict(list)
        maybe_edges = defaultdict(list)
        maybe_assocs = []
        maybe_multi_hops = []

        records = split_string_by_multi_markers(
            result,
            [context_base["record_delimiter"], context_base["completion_delimiter"]],
        )

        for record in records:
            record = re.search(r"\((.*)\)", record)
            if record is None:
                continue
            record = record.group(1)
            record_attributes = split_string_by_multi_markers(
                record, [context_base["tuple_delimiter"]]
            )

            if_entities = await _handle_single_entity_extraction(
                record_attributes, chunk_key, file_path
            )
            if if_entities is not None:
                maybe_nodes[if_entities["entity_name"]].append(if_entities)
                continue

            if_relation = await _handle_single_relationship_extraction(
                record_attributes, chunk_key, file_path
            )
            if if_relation is not None:
                maybe_edges[(if_relation["src_id"], if_relation["tgt_id"])].append(
                    if_relation
                )
                continue

            if global_config.get("enable_latent_relation", True):
                if_latent = await _handle_single_latent_relation_extraction(
                    record_attributes, chunk_key, file_path
                )
                if if_latent is not None:
                    maybe_edges[(if_latent["src_id"], if_latent["tgt_id"])].append(
                        if_latent
                    )
                    continue

            if global_config.get("enable_multi_hop", True):
                if_multi = await _handle_single_multi_hop_extraction(
                    record_attributes, chunk_key, file_path
                )
                if if_multi is not None:
                    maybe_multi_hops.append(if_multi)
                    continue

            if global_config.get("enable_association", True):
                if_assoc = await _handle_single_association_extraction(
                    record_attributes, chunk_key, file_path
                )
                if if_assoc is not None:
                    maybe_assocs.append(if_assoc)

        return maybe_nodes, maybe_edges, maybe_assocs, maybe_multi_hops

    async def _process_single_content(chunk_key_dp: tuple[str, TextChunkSchema]):
        """Process a single chunk
        Args:
            chunk_key_dp (tuple[str, TextChunkSchema]):
                ("chunk-xxxxxx", {"tokens": int, "content": str, "full_doc_id": str, "chunk_order_index": int})
        Returns:
            tuple: (maybe_nodes, maybe_edges) containing extracted entities and relationships
        """
        nonlocal processed_chunks
        chunk_key = chunk_key_dp[0]
        chunk_dp = chunk_key_dp[1]
        content = chunk_dp["content"]
        # Get file path from chunk data or use default
        file_path = chunk_dp.get("file_path", "unknown_source")

        # Get initial extraction
        hint_prompt = entity_extract_prompt.format(
            **{**context_base, "input_text": content}
        )

        final_result = await use_llm_func_with_cache(
            hint_prompt,
            use_llm_func,
            llm_response_cache=llm_response_cache,
            cache_type="extract",
        )
        history = pack_user_ass_to_openai_messages(hint_prompt, final_result)

        # Process initial extraction with file path
        (
            maybe_nodes,
            maybe_edges,
            maybe_assocs,
            maybe_multi_hops,
        ) = await _process_extraction_result(final_result, chunk_key, file_path)

        # Process additional gleaning results
        for now_glean_index in range(entity_extract_max_gleaning):
            glean_result = await use_llm_func_with_cache(
                continue_prompt,
                use_llm_func,
                llm_response_cache=llm_response_cache,
                history_messages=history,
                cache_type="extract",
            )

            history += pack_user_ass_to_openai_messages(continue_prompt, glean_result)

            # Process gleaning result separately with file path
            (
                glean_nodes,
                glean_edges,
                glean_assocs,
                glean_multis,
            ) = await _process_extraction_result(glean_result, chunk_key, file_path)

            # Merge results - only add entities and edges with new names
            for entity_name, entities in glean_nodes.items():
                if (
                    entity_name not in maybe_nodes
                ):  # Only accetp entities with new name in gleaning stage
                    maybe_nodes[entity_name].extend(entities)
            for edge_key, edges in glean_edges.items():
                if edge_key not in maybe_edges:
                    maybe_edges[edge_key].extend(edges)
            for assoc in glean_assocs:
                maybe_assocs.append(assoc)
            for mh in glean_multis:
                maybe_multi_hops.append(mh)

            if now_glean_index == entity_extract_max_gleaning - 1:
                break

            if_loop_result: str = await use_llm_func_with_cache(
                if_loop_prompt,
                use_llm_func,
                llm_response_cache=llm_response_cache,
                history_messages=history,
                cache_type="extract",
            )
            if_loop_result = if_loop_result.strip().strip('"').strip("'").lower()
            if if_loop_result != "yes":
                break

        processed_chunks += 1
        entities_count = len(maybe_nodes)
        relations_count = len(maybe_edges)
        assoc_count = len(maybe_assocs)
        multi_count = len(maybe_multi_hops)
        log_message = f"Chunk {processed_chunks} of {total_chunks} extracted {entities_count} Ent + {relations_count} Rel + {assoc_count} Assoc + {multi_count} Multi"
        logger.info(log_message)
        if pipeline_status is not None:
            async with pipeline_status_lock:
                pipeline_status["latest_message"] = log_message
                pipeline_status["history_messages"].append(log_message)

        # Return the extracted nodes, edges, associations and multi-hop paths
        return maybe_nodes, maybe_edges, maybe_assocs, maybe_multi_hops

    # Get max async tasks limit from global_config
    llm_model_max_async = global_config.get("llm_model_max_async", 4)
    semaphore = asyncio.Semaphore(llm_model_max_async)

    async def _process_with_semaphore(chunk):
        async with semaphore:
            return await _process_single_content(chunk)

    tasks = []
    for c in ordered_chunks:
        task = asyncio.create_task(_process_with_semaphore(c))
        tasks.append(task)

    # Wait for tasks to complete or for the first exception to occur
    # This allows us to cancel remaining tasks if any task fails
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)

    # Check if any task raised an exception
    for task in done:
        if task.exception():
            # If a task failed, cancel all pending tasks
            # This prevents unnecessary processing since the parent function will abort anyway
            for pending_task in pending:
                pending_task.cancel()

            # Wait for cancellation to complete
            if pending:
                await asyncio.wait(pending)

            # Re-raise the exception to notify the caller
            raise task.exception()

    # If all tasks completed successfully, collect results
    chunk_results = [task.result() for task in tasks]

    # Return the chunk_results for later processing in merge_nodes_and_edges
    return chunk_results


async def kg_query(
    query: str,
    knowledge_graph_inst: BaseGraphStorage,
    entities_vdb: BaseVectorStorage,
    relationships_vdb: BaseVectorStorage,
    text_chunks_db: BaseKVStorage,
    query_param: QueryParam,
    global_config: dict[str, str],
    hashing_kv: BaseKVStorage | None = None,
    system_prompt: str | None = None,
    chunks_vdb: BaseVectorStorage = None,
) -> str | AsyncIterator[str]:
    if query_param.user_profile:
        query = personalize_query(query, query_param.user_profile)

    if query_param.model_func:
        use_model_func = query_param.model_func
    else:
        use_model_func = global_config["llm_model_func"]
        # Apply higher priority (5) to query relation LLM function
        use_model_func = partial(use_model_func, _priority=5)

    # Handle cache
    args_hash = compute_args_hash(query_param.mode, query, cache_type="query")
    cached_response, quantized, min_val, max_val = await handle_cache(
        hashing_kv, args_hash, query, query_param.mode, cache_type="query"
    )
    if cached_response is not None:
        return cached_response

    hl_keywords, ll_keywords, community = await get_keywords_from_query(
        query, query_param, global_config, hashing_kv
    )

    logger.debug(f"High-level keywords: {hl_keywords}")
    logger.debug(f"Low-level  keywords: {ll_keywords}")

    # Handle empty keywords
    if hl_keywords == [] and ll_keywords == []:
        logger.warning("low_level_keywords and high_level_keywords is empty")
        return PROMPTS["fail_response"]
    if ll_keywords == [] and query_param.mode in ["local", "hybrid"]:
        logger.warning(
            "low_level_keywords is empty, switching from %s mode to global mode",
            query_param.mode,
        )
        query_param.mode = "global"
    if hl_keywords == [] and query_param.mode in ["global", "hybrid"]:
        logger.warning(
            "high_level_keywords is empty, switching from %s mode to local mode",
            query_param.mode,
        )
        query_param.mode = "local"

    ll_keywords_str = ", ".join(ll_keywords) if ll_keywords else ""
    hl_keywords_str = ", ".join(hl_keywords) if hl_keywords else ""
    community_str = community if community else ""

    # Build context
    context = await _build_query_context(
        ll_keywords_str,
        hl_keywords_str,
        community_str,
        knowledge_graph_inst,
        entities_vdb,
        relationships_vdb,
        text_chunks_db,
        query_param,
        chunks_vdb,
        global_config,
        hashing_kv=hashing_kv,
    )

    if query_param.only_need_context:
        return context
    if context is None:
        return PROMPTS["fail_response"]

    # Process conversation history
    history_context = ""
    if query_param.conversation_history:
        history_context = get_conversation_turns(
            query_param.conversation_history, query_param.history_turns
        )

    # Build system prompt
    user_prompt = (
        query_param.user_prompt
        if query_param.user_prompt
        else PROMPTS["DEFAULT_USER_PROMPT"]
    )
    sys_prompt_temp = system_prompt if system_prompt else PROMPTS["rag_response"]
    sys_prompt = sys_prompt_temp.format(
        context_data=context,
        response_type=query_param.response_type,
        history=history_context,
        user_prompt=user_prompt,
        user_profile=json.dumps(query_param.user_profile, ensure_ascii=False),
    )

    if query_param.only_need_prompt:
        return sys_prompt

    tokenizer: Tokenizer = global_config["tokenizer"]
    len_of_prompts = len(tokenizer.encode(query + sys_prompt))
    logger.debug(f"[kg_query]Prompt Tokens: {len_of_prompts}")

    response = await use_model_func(
        query,
        system_prompt=sys_prompt,
        stream=query_param.stream,
    )
    if isinstance(response, str) and len(response) > len(sys_prompt):
        response = (
            response.replace(sys_prompt, "")
            .replace("user", "")
            .replace("model", "")
            .replace(query, "")
            .replace("<system>", "")
            .replace("</system>", "")
            .strip()
        )

    if hashing_kv.global_config.get("enable_llm_cache"):
        # Save to cache
        await save_to_cache(
            hashing_kv,
            CacheData(
                args_hash=args_hash,
                content=response,
                prompt=query,
                quantized=quantized,
                min_val=min_val,
                max_val=max_val,
                mode=query_param.mode,
                cache_type="query",
            ),
        )

    return response


async def get_keywords_from_query(
    query: str,
    query_param: QueryParam,
    global_config: dict[str, str],
    hashing_kv: BaseKVStorage | None = None,
) -> tuple[list[str], list[str], str]:
    """
    Retrieves high-level and low-level keywords for RAG operations.

    This function checks if keywords are already provided in query parameters,
    and if not, extracts them from the query text using LLM.

    Args:
        query: The user's query text
        query_param: Query parameters that may contain pre-defined keywords
        global_config: Global configuration dictionary
        hashing_kv: Optional key-value storage for caching results

    Returns:
        A tuple containing (high_level_keywords, low_level_keywords)
    """
    # Check if pre-defined keywords are already provided
    if query_param.hl_keywords or query_param.ll_keywords:
        return query_param.hl_keywords, query_param.ll_keywords, ""

    # Extract keywords using extract_keywords_only function which already supports conversation history
    hl_keywords, ll_keywords, community = await extract_keywords_only(
        query, query_param, global_config, hashing_kv
    )
    return hl_keywords, ll_keywords, community


async def extract_keywords_only(
    text: str,
    param: QueryParam,
    global_config: dict[str, str],
    hashing_kv: BaseKVStorage | None = None,
) -> tuple[list[str], list[str], str]:
    """
    Extract high-level and low-level keywords from the given 'text' using the LLM.
    This method does NOT build the final RAG context or provide a final answer.
    It ONLY extracts keywords (hl_keywords, ll_keywords).
    """

    # 1. Handle cache if needed - add cache type for keywords
    args_hash = compute_args_hash(param.mode, text, cache_type="keywords")
    cached_response, quantized, min_val, max_val = await handle_cache(
        hashing_kv, args_hash, text, param.mode, cache_type="keywords"
    )
    if cached_response is not None:
        try:
            keywords_data = json.loads(cached_response)
            return (
                keywords_data.get("high_level_keywords", []),
                keywords_data.get("low_level_keywords", []),
                keywords_data.get("Community", ""),
            )
        except (json.JSONDecodeError, KeyError):
            logger.warning(
                "Invalid cache format for keywords, proceeding with extraction"
            )

    # 2. Build the examples
    example_number = global_config["addon_params"].get("example_number", None)
    if example_number and example_number < len(PROMPTS["keywords_extraction_examples"]):
        examples = "\n".join(
            PROMPTS["keywords_extraction_examples"][: int(example_number)]
        )
    else:
        examples = "\n".join(PROMPTS["keywords_extraction_examples"])
    language = global_config["addon_params"].get(
        "language", PROMPTS["DEFAULT_LANGUAGE"]
    )

    # 3. Process conversation history
    history_context = ""
    if param.conversation_history:
        history_context = get_conversation_turns(
            param.conversation_history, param.history_turns
        )

    # 4. Build the keyword-extraction prompt
    kw_prompt = PROMPTS["keywords_extraction"].format(
        query=text, examples=examples, language=language, history=history_context
    )

    tokenizer: Tokenizer = global_config["tokenizer"]
    len_of_prompts = len(tokenizer.encode(kw_prompt))
    logger.debug(f"[kg_query]Prompt Tokens: {len_of_prompts}")

    # 5. Call the LLM for keyword extraction
    if param.model_func:
        use_model_func = param.model_func
    else:
        use_model_func = global_config["llm_model_func"]
        # Apply higher priority (5) to query relation LLM function
        use_model_func = partial(use_model_func, _priority=5)

    result = await use_model_func(kw_prompt, keyword_extraction=True)

    # 6. Parse out JSON from the LLM response
    match = re.search(r"\{.*\}", result, re.DOTALL)
    if not match:
        logger.error("No JSON-like structure found in the LLM respond.")
        return [], []
    try:
        keywords_data = json.loads(match.group(0))
    except json.JSONDecodeError as e:
        logger.error(f"JSON parsing error: {e}")
        return [], []

    hl_keywords = keywords_data.get("high_level_keywords", [])
    ll_keywords = keywords_data.get("low_level_keywords", [])
    community = keywords_data.get("Community", "")

    # 7. Cache only the processed keywords with cache type
    if hl_keywords or ll_keywords or community:
        cache_data = {
            "high_level_keywords": hl_keywords,
            "low_level_keywords": ll_keywords,
            "Community": community,
        }
        if hashing_kv.global_config.get("enable_llm_cache"):
            await save_to_cache(
                hashing_kv,
                CacheData(
                    args_hash=args_hash,
                    content=json.dumps(cache_data),
                    prompt=text,
                    quantized=quantized,
                    min_val=min_val,
                    max_val=max_val,
                    mode=param.mode,
                    cache_type="keywords",
                ),
            )

    return hl_keywords, ll_keywords, community


async def _get_vector_context(
    query: str,
    chunks_vdb: BaseVectorStorage,
    query_param: QueryParam,
    tokenizer: Tokenizer,
    global_config: dict | None = None,
    llm_response_cache: BaseKVStorage | None = None,
) -> tuple[list, list, list] | None:
    """
    Retrieve vector context from the vector database.

    This function performs vector search to find relevant text chunks for a query,
    formats them with file path and creation time information.

    Args:
        query: The query string to search for
        chunks_vdb: Vector database containing document chunks
        query_param: Query parameters including top_k and ids
        tokenizer: Tokenizer for counting tokens

    Returns:
        Tuple (empty_entities, empty_relations, text_units) for combine_contexts,
        compatible with _get_edge_data and _get_node_data format
    """
    try:
        fetch_k = query_param.top_k * query_param.page
        results = await chunks_vdb.query(query, top_k=fetch_k, ids=query_param.ids)
        if not results:
            return [], [], []

        valid_chunks = []
        for result in results:
            if "content" in result:
                # Directly use content from chunks_vdb.query result
                chunk_with_time = {
                    "content": result["content"],
                    "created_at": result.get("created_at", None),
                    "file_path": result.get("file_path", "unknown_source"),
                }
                valid_chunks.append(chunk_with_time)

        if not valid_chunks:
            return [], [], []

        maybe_trun_chunks = truncate_list_by_token_size(
            valid_chunks,
            key=lambda x: x["content"],
            max_token_size=query_param.max_token_for_text_unit,
            tokenizer=tokenizer,
        )
        offset = query_param.top_k * (query_param.page - 1)
        maybe_trun_chunks = maybe_trun_chunks[offset : offset + query_param.top_k]

        logger.debug(
            f"Truncate chunks from {len(valid_chunks)} to {len(maybe_trun_chunks)} (max tokens:{query_param.max_token_for_text_unit})"
        )
        logger.info(
            f"Vector query: {len(maybe_trun_chunks)} chunks, top_k: {query_param.top_k}"
        )

        if not maybe_trun_chunks:
            return [], [], []

        # Create empty entities and relations contexts
        entities_context = []
        relations_context = []

        # Create text_units_context directly as a list of dictionaries
        text_units_context = []
        summary_tokens = 500
        if global_config is not None:
            summary_tokens = global_config.get("summary_to_max_tokens", 500)
        for i, chunk in enumerate(maybe_trun_chunks):
            if len(tokenizer.encode(chunk["content"])) > summary_tokens:
                chunk["content"] = await _handle_entity_relation_summary(
                    "chunk",
                    chunk["content"],
                    global_config or {},
                    llm_response_cache=llm_response_cache,
                )
            text_units_context.append(
                {
                    "id": i + 1,
                    "content": chunk["content"],
                    "file_path": chunk["file_path"],
                }
            )

        return entities_context, relations_context, text_units_context
    except Exception as e:
        logger.error(f"Error in _get_vector_context: {e}")
        return [], [], []


async def _build_query_context(
    ll_keywords: str,
    hl_keywords: str,
    community: str,
    knowledge_graph_inst: BaseGraphStorage,
    entities_vdb: BaseVectorStorage,
    relationships_vdb: BaseVectorStorage,
    text_chunks_db: BaseKVStorage,
    query_param: QueryParam,
    chunks_vdb: BaseVectorStorage = None,  # Add chunks_vdb parameter for mix mode
    global_config: dict | None = None,
    hashing_kv: BaseKVStorage | None = None,
    llm_response_cache: BaseKVStorage | None = None,
):
    logger.info(f"Process {os.getpid()} building query context...")

    # Handle local and global modes as before
    if query_param.mode == "local":
        entities_context, relations_context, text_units_context = await _get_node_data(
            f"{ll_keywords} {community}".strip(),
            knowledge_graph_inst,
            entities_vdb,
            text_chunks_db,
            query_param,
            global_config,
            llm_response_cache,
        )
    elif query_param.mode == "global":
        entities_context, relations_context, text_units_context = await _get_edge_data(
            f"{hl_keywords} {community}".strip(),
            knowledge_graph_inst,
            relationships_vdb,
            text_chunks_db,
            query_param,
            global_config,
            llm_response_cache,
        )
    else:  # hybrid or mix mode
        ll_data = await _get_node_data(
            f"{ll_keywords} {community}".strip(),
            knowledge_graph_inst,
            entities_vdb,
            text_chunks_db,
            query_param,
            global_config,
            llm_response_cache,
        )
        hl_data = await _get_edge_data(
            f"{hl_keywords} {community}".strip(),
            knowledge_graph_inst,
            relationships_vdb,
            text_chunks_db,
            query_param,
            global_config,
            llm_response_cache,
        )

        (
            ll_entities_context,
            ll_relations_context,
            ll_text_units_context,
        ) = ll_data

        (
            hl_entities_context,
            hl_relations_context,
            hl_text_units_context,
        ) = hl_data

        # Initialize vector data with empty lists
        vector_entities_context, vector_relations_context, vector_text_units_context = (
            [],
            [],
            [],
        )

        # Only get vector data if in mix mode
        if query_param.mode == "mix" and hasattr(query_param, "original_query"):
            # Get tokenizer from text_chunks_db
            tokenizer = text_chunks_db.global_config.get("tokenizer")

            # Get vector context in triple format
            vector_data = await _get_vector_context(
                query_param.original_query,
                chunks_vdb,
                query_param,
                tokenizer,
                global_config,
                llm_response_cache,
            )

            # If vector_data is not None, unpack it
            if vector_data is not None:
                (
                    vector_entities_context,
                    vector_relations_context,
                    vector_text_units_context,
                ) = vector_data

        # Combine and deduplicate the entities, relationships, and sources
        entities_context = process_combine_contexts(
            hl_entities_context, ll_entities_context, vector_entities_context
        )
        relations_context = process_combine_contexts(
            hl_relations_context, ll_relations_context, vector_relations_context
        )
        text_units_context = process_combine_contexts(
            hl_text_units_context, ll_text_units_context, vector_text_units_context
        )
    # not necessary to use LLM to generate a response
    if not entities_context and not relations_context:
        return None

    multi_hop_context = []
    if global_config is None or global_config.get("enable_multi_hop", True):
        multi_hop_context = await _collect_multi_hop_paths(
            entities_context,
            knowledge_graph_inst,
            top_k=query_param.top_k,
            hashing_kv=hashing_kv,
            min_strength=global_config.get("multi_hop_min_strength", 0.0),
            keywords=query_param.hl_keywords + query_param.ll_keywords,
        )

    base_url = os.getenv("ENTITY_LINK_BASE_URL", DEFAULT_ENTITY_LINK_BASE_URL)
    (
        entities_prompt,
        relations_prompt,
        multi_hop_prompt,
    ) = _add_entity_links(
        entities_context, relations_context, multi_hop_context, base_url
    )

    entities_str = json.dumps(entities_prompt, ensure_ascii=False)
    relations_str = json.dumps(relations_prompt, ensure_ascii=False)
    text_units_str = json.dumps(text_units_context, ensure_ascii=False)
    multi_hop_str = json.dumps(multi_hop_prompt, ensure_ascii=False)

    result = f"""-----Entities(KG)-----
{entities_str}

-----Relationships(KG)-----
{relations_str}

-----Multi-hop Paths-----
{multi_hop_str}

-----Document Chunks(DC)-----
{text_units_str}
"""
    return result


async def _get_node_data(
    query: str,
    knowledge_graph_inst: BaseGraphStorage,
    entities_vdb: BaseVectorStorage,
    text_chunks_db: BaseKVStorage,
    query_param: QueryParam,
    global_config: dict | None = None,
    llm_response_cache: BaseKVStorage | None = None,
):
    # get similar entities
    logger.info(
        f"Query nodes: {query}, top_k: {query_param.top_k}, cosine: {entities_vdb.cosine_better_than_threshold}"
    )

    # Support pagination by requesting more results then slicing
    fetch_k = query_param.top_k * query_param.page
    results = await entities_vdb.query(query, top_k=fetch_k, ids=query_param.ids)

    if not len(results):
        # Fallback: direct lookup by standardized name
        normalized = standardize_entity_name(query)
        node = await knowledge_graph_inst.get_node(normalized)
        if node:
            node_datas = [
                {
                    **node,
                    "entity_name": normalized,
                    "rank": 1.0,
                    "created_at": node.get("created_at"),
                }
            ]
            use_text_units = await _find_most_related_text_unit_from_entities(
                node_datas,
                query_param,
                text_chunks_db,
                knowledge_graph_inst,
                global_config,
                llm_response_cache,
            )
            use_relations = await _find_most_related_edges_from_entities(
                node_datas,
                query_param,
                knowledge_graph_inst,
            )
            tokenizer: Tokenizer = text_chunks_db.global_config.get("tokenizer")
            node_datas = truncate_list_by_token_size(
                node_datas,
                key=lambda x: x.get("description", ""),
                max_token_size=query_param.max_token_for_local_context,
                tokenizer=tokenizer,
            )
            return node_datas, use_relations, use_text_units
        return "", "", ""

    # Extract all entity IDs from your results list
    node_ids = [r["entity_name"] for r in results]

    # Call the batch node retrieval and degree functions concurrently.
    nodes_dict, degrees_dict = await asyncio.gather(
        knowledge_graph_inst.get_nodes_batch(node_ids),
        knowledge_graph_inst.node_degrees_batch(node_ids),
    )

    # Now, if you need the node data and degree in order:
    node_datas = [nodes_dict.get(nid) for nid in node_ids]
    node_degrees = [degrees_dict.get(nid, 0) for nid in node_ids]

    if not all([n is not None for n in node_datas]):
        logger.warning("Some nodes are missing, maybe the storage is damaged")

    filtered_nodes = []
    cat_filter = [c.lower() for c in query_param.categories]
    for k, n, d in zip(results, node_datas, node_degrees):
        if n is None:
            continue
        if query_param.degree_threshold and d < query_param.degree_threshold:
            continue
        if (
            query_param.similarity_threshold
            and k.get("distance", 1.0) > query_param.similarity_threshold
        ):
            continue
        if cat_filter:
            comm = str(n.get("entity_community", "")).lower()
            if comm not in cat_filter:
                continue
        filtered_nodes.append(
            {
                **n,
                "entity_name": k["entity_name"],
                "rank": d,
                "created_at": k.get("created_at"),
            }
        )

    node_datas = filtered_nodes

    for nd in node_datas:
        score = 0.0
        for other in node_datas:
            if nd["entity_name"] == other["entity_name"]:
                continue
            length = await knowledge_graph_inst.shortest_path_length(
                nd["entity_name"], other["entity_name"]
            )
            if length != -1:
                score += 1 / (length + 1)
        nd["connectivity"] = score

    node_datas = sorted(
        node_datas, key=lambda x: (x["rank"], x["connectivity"]), reverse=True
    )
    offset = query_param.top_k * (query_param.page - 1)
    node_datas = node_datas[offset : offset + query_param.top_k]
    # get entitytext chunk
    use_text_units = await _find_most_related_text_unit_from_entities(
        node_datas,
        query_param,
        text_chunks_db,
        knowledge_graph_inst,
        global_config,
        llm_response_cache,
    )
    use_relations = await _find_most_related_edges_from_entities(
        node_datas,
        query_param,
        knowledge_graph_inst,
    )

    tokenizer: Tokenizer = text_chunks_db.global_config.get("tokenizer")
    len_node_datas = len(node_datas)
    node_datas = truncate_list_by_token_size(
        node_datas,
        key=lambda x: x.get("description", "") or "",
        max_token_size=query_param.max_token_for_local_context,
        tokenizer=tokenizer,
    )
    logger.debug(
        f"Truncate entities from {len_node_datas} to {len(node_datas)} (max tokens:{query_param.max_token_for_local_context})"
    )

    logger.info(
        f"Local query uses {len(node_datas)} entites, {len(use_relations)} relations, {len(use_text_units)} chunks"
    )

    # build prompt
    entities_context = []
    for i, n in enumerate(node_datas):
        created_at = n.get("created_at", "UNKNOWN")
        if isinstance(created_at, (int, float)):
            created_at = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(created_at))

        # Get file path from node data
        file_path = n.get("file_path", "unknown_source")

        desc = n.get("description", "UNKNOWN")
        if n.get("additional_properties"):
            desc += f"\n{n['additional_properties']}"
        if n.get("entity_community"):
            desc += f"\n{n['entity_community']}"

        entities_context.append(
            {
                "id": i + 1,
                "entity": n["entity_name"],
                "type": n.get("entity_type", "UNKNOWN"),
                "description": desc,
                "rank": n["rank"],
                "created_at": created_at,
                "file_path": file_path,
            }
        )

    relations_context = []
    for i, e in enumerate(use_relations):
        created_at = e.get("created_at", "UNKNOWN")
        # Convert timestamp to readable format
        if isinstance(created_at, (int, float)):
            created_at = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(created_at))

        # Get file path from edge data
        file_path = e.get("file_path", "unknown_source")

        relations_context.append(
            {
                "id": i + 1,
                "entity1": e["src_tgt"][0],
                "entity2": e["src_tgt"][1],
                "description": e["description"],
                "keywords": e["keywords"],
                "weight": e["weight"],
                "rank": e["rank"],
                "created_at": created_at,
                "file_path": file_path,
            }
        )

    text_units_context = []
    for i, t in enumerate(use_text_units):
        text_units_context.append(
            {
                "id": i + 1,
                "content": t["content"],
                "file_path": t.get("file_path", "unknown_source"),
            }
        )
    return entities_context, relations_context, text_units_context


async def _find_most_related_text_unit_from_entities(
    node_datas: list[dict],
    query_param: QueryParam,
    text_chunks_db: BaseKVStorage,
    knowledge_graph_inst: BaseGraphStorage,
    global_config: dict | None = None,
    llm_response_cache: BaseKVStorage | None = None,
):
    text_units = []
    for dp in node_datas:
        source_id = dp.get("source_id")
        if source_id is not None:
            text_units.append(
                split_string_by_multi_markers(source_id, [GRAPH_FIELD_SEP])
            )

    node_names = [dp["entity_name"] for dp in node_datas]
    batch_edges_dict = await knowledge_graph_inst.get_nodes_edges_batch(node_names)
    # Build the edges list in the same order as node_datas.
    edges = [batch_edges_dict.get(name, []) for name in node_names]

    all_one_hop_nodes = set()
    for this_edges in edges:
        if not this_edges:
            continue
        all_one_hop_nodes.update([e[1] for e in this_edges])

    all_one_hop_nodes = list(all_one_hop_nodes)

    # Batch retrieve one-hop node data using get_nodes_batch
    all_one_hop_nodes_data_dict = await knowledge_graph_inst.get_nodes_batch(
        all_one_hop_nodes
    )
    all_one_hop_nodes_data = [
        all_one_hop_nodes_data_dict.get(e) for e in all_one_hop_nodes
    ]

    # Add null check for node data
    all_one_hop_text_units_lookup = {
        k: set(split_string_by_multi_markers(v["source_id"], [GRAPH_FIELD_SEP]))
        for k, v in zip(all_one_hop_nodes, all_one_hop_nodes_data)
        if v is not None and "source_id" in v  # Add source_id check
    }

    all_text_units_lookup = {}
    tasks = []

    for index, (this_text_units, this_edges) in enumerate(zip(text_units, edges)):
        for c_id in this_text_units:
            if c_id not in all_text_units_lookup:
                all_text_units_lookup[c_id] = index
                tasks.append((c_id, index, this_edges))

    # Process in batches tasks at a time to avoid overwhelming resources
    batch_size = 5
    results = []

    for i in range(0, len(tasks), batch_size):
        batch_tasks = tasks[i : i + batch_size]
        batch_results = await asyncio.gather(
            *[text_chunks_db.get_by_id(c_id) for c_id, _, _ in batch_tasks]
        )
        results.extend(batch_results)

    for (c_id, index, this_edges), data in zip(tasks, results):
        all_text_units_lookup[c_id] = {
            "data": data,
            "order": index,
            "relation_counts": 0,
            "connectivity": node_datas[index].get("connectivity", 0),
        }

        if this_edges:
            for e in this_edges:
                if (
                    e[1] in all_one_hop_text_units_lookup
                    and c_id in all_one_hop_text_units_lookup[e[1]]
                ):
                    all_text_units_lookup[c_id]["relation_counts"] += 1

    # Filter out None values and ensure data has content
    all_text_units = [
        {"id": k, **v}
        for k, v in all_text_units_lookup.items()
        if v is not None and v.get("data") is not None and "content" in v["data"]
    ]

    if not all_text_units:
        logger.warning("No valid text units found")
        return []

    tokenizer: Tokenizer = text_chunks_db.global_config.get("tokenizer")
    all_text_units = sorted(
        all_text_units,
        key=lambda x: (
            x["order"],
            -x["relation_counts"],
            -x.get("connectivity", 0),
        ),
    )
    all_text_units = truncate_list_by_token_size(
        all_text_units,
        key=lambda x: x["data"]["content"],
        max_token_size=query_param.max_token_for_text_unit,
        tokenizer=tokenizer,
    )

    logger.debug(
        f"Truncate chunks from {len(all_text_units_lookup)} to {len(all_text_units)} (max tokens:{query_param.max_token_for_text_unit})"
    )

    summary_tokens = 0
    if global_config is not None:
        summary_tokens = global_config.get("summary_to_max_tokens", 500)
    summarized = []
    for t in all_text_units:
        if global_config is not None:
            tok = tokenizer.encode(t["data"]["content"])
            if len(tok) > summary_tokens:
                t["data"]["content"] = await _handle_entity_relation_summary(
                    "chunk",
                    t["data"]["content"],
                    global_config,
                    llm_response_cache=llm_response_cache,
                )
        summarized.append(t["data"])
    return summarized


async def _find_most_related_edges_from_entities(
    node_datas: list[dict],
    query_param: QueryParam,
    knowledge_graph_inst: BaseGraphStorage,
):
    node_names = [dp["entity_name"] for dp in node_datas]
    batch_edges_dict = await knowledge_graph_inst.get_nodes_edges_batch(node_names)

    all_edges = []
    seen = set()

    for node_name in node_names:
        this_edges = batch_edges_dict.get(node_name, [])
        for e in this_edges:
            sorted_edge = tuple(sorted(e))
            if sorted_edge not in seen:
                seen.add(sorted_edge)
                all_edges.append(sorted_edge)

    # Prepare edge pairs in two forms:
    # For the batch edge properties function, use dicts.
    edge_pairs_dicts = [{"src": e[0], "tgt": e[1]} for e in all_edges]
    # For edge degrees, use tuples.
    edge_pairs_tuples = list(all_edges)  # all_edges is already a list of tuples

    # Call the batched functions concurrently.
    edge_data_dict, edge_degrees_dict = await asyncio.gather(
        knowledge_graph_inst.get_edges_batch(edge_pairs_dicts),
        knowledge_graph_inst.edge_degrees_batch(edge_pairs_tuples),
    )

    # Reconstruct edge_datas list in the same order as the deduplicated results.
    all_edges_data = []
    for pair in all_edges:
        edge_props = edge_data_dict.get(pair)
        if edge_props is not None:
            if "weight" not in edge_props:
                logger.warning(
                    f"Edge {pair} missing 'weight' attribute, using default value 0.0"
                )
                edge_props["weight"] = 0.0

            connectivity = 0.0
            for nd in node_datas:
                ent = nd["entity_name"]
                if ent in pair:
                    continue
                l1 = await knowledge_graph_inst.shortest_path_length(pair[0], ent)
                l2 = await knowledge_graph_inst.shortest_path_length(pair[1], ent)
                lengths = [val for val in (l1, l2) if val != -1]
                if lengths:
                    connectivity += 1 / (min(lengths) + 1)

            combined = {
                "src_tgt": pair,
                "rank": edge_degrees_dict.get(pair, 0),
                "connectivity": connectivity,
                **edge_props,
            }
            all_edges_data.append(combined)

    tokenizer: Tokenizer = knowledge_graph_inst.global_config.get("tokenizer")
    all_edges_data = sorted(
        all_edges_data,
        key=lambda x: (x["rank"], x.get("weight", 0), x.get("connectivity", 0)),
        reverse=True,
    )
    all_edges_data = truncate_list_by_token_size(
        all_edges_data,
        key=lambda x: x["description"] if x["description"] is not None else "",
        max_token_size=query_param.max_token_for_global_context,
        tokenizer=tokenizer,
    )

    logger.debug(
        f"Truncate relations from {len(all_edges)} to {len(all_edges_data)} (max tokens:{query_param.max_token_for_global_context})"
    )

    return all_edges_data


async def _get_edge_data(
    keywords,
    knowledge_graph_inst: BaseGraphStorage,
    relationships_vdb: BaseVectorStorage,
    text_chunks_db: BaseKVStorage,
    query_param: QueryParam,
    global_config: dict | None = None,
    llm_response_cache: BaseKVStorage | None = None,
):
    logger.info(
        f"Query edges: {keywords}, top_k: {query_param.top_k}, cosine: {relationships_vdb.cosine_better_than_threshold}"
    )

    fetch_k = query_param.top_k * query_param.page
    results = await relationships_vdb.query(
        keywords, top_k=fetch_k, ids=query_param.ids
    )

    if not len(results):
        return "", "", ""

    # Prepare edge pairs in two forms:
    # For the batch edge properties function, use dicts.
    edge_pairs_dicts = [{"src": r["src_id"], "tgt": r["tgt_id"]} for r in results]
    # For edge degrees, use tuples.
    edge_pairs_tuples = [(r["src_id"], r["tgt_id"]) for r in results]

    # Call the batched functions concurrently.
    edge_data_dict, edge_degrees_dict = await asyncio.gather(
        knowledge_graph_inst.get_edges_batch(edge_pairs_dicts),
        knowledge_graph_inst.edge_degrees_batch(edge_pairs_tuples),
    )

    # Reconstruct edge_datas list in the same order as results.
    edge_datas = []
    cat_filter = [c.lower() for c in query_param.categories]
    for k in results:
        pair = (k["src_id"], k["tgt_id"])
        edge_props = edge_data_dict.get(pair)
        if edge_props is None:
            continue
        deg = edge_degrees_dict.get(pair, k.get("rank", 0))
        if query_param.degree_threshold and deg < query_param.degree_threshold:
            continue
        if (
            query_param.similarity_threshold
            and k.get("distance", 1.0) > query_param.similarity_threshold
        ):
            continue
        if cat_filter:
            kw = str(edge_props.get("keywords", "")).lower()
            if not any(c in kw for c in cat_filter):
                continue
        if "weight" not in edge_props:
            logger.warning(
                f"Edge {pair} missing 'weight' attribute, using default value 0.0"
            )
            edge_props["weight"] = 0.0

        combined = {
            "src_id": k["src_id"],
            "tgt_id": k["tgt_id"],
            "rank": deg,
            "created_at": k.get("created_at", None),
            **edge_props,
        }
        edge_datas.append(combined)

    tokenizer: Tokenizer = text_chunks_db.global_config.get("tokenizer")
    edge_datas = sorted(
        edge_datas,
        key=lambda x: (x["rank"], x.get("weight", 0)),
        reverse=True,
    )
    offset = query_param.top_k * (query_param.page - 1)
    edge_datas = edge_datas[offset : offset + query_param.top_k]
    edge_datas = truncate_list_by_token_size(
        edge_datas,
        key=lambda x: x["description"] if x["description"] is not None else "",
        max_token_size=query_param.max_token_for_global_context,
        tokenizer=tokenizer,
    )
    use_entities, use_text_units = await asyncio.gather(
        _find_most_related_entities_from_relationships(
            edge_datas,
            query_param,
            knowledge_graph_inst,
        ),
        _find_related_text_unit_from_relationships(
            edge_datas,
            query_param,
            text_chunks_db,
            knowledge_graph_inst,
        ),
    )

    for e in edge_datas:
        score = 0.0
        for n in use_entities:
            ent = n["entity_name"]
            if ent in (e["src_id"], e["tgt_id"]):
                continue
            l1 = await knowledge_graph_inst.shortest_path_length(e["src_id"], ent)
            l2 = await knowledge_graph_inst.shortest_path_length(e["tgt_id"], ent)
            lengths = [val for val in (l1, l2) if val != -1]
            if lengths:
                score += 1 / (min(lengths) + 1)
        e["connectivity"] = score

    edge_datas = sorted(
        edge_datas,
        key=lambda x: (
            x["rank"],
            x.get("weight", 0),
            x.get("connectivity", 0),
        ),
        reverse=True,
    )
    logger.info(
        f"Global query uses {len(use_entities)} entites, {len(edge_datas)} relations, {len(use_text_units)} chunks"
    )

    relations_context = []
    for i, e in enumerate(edge_datas):
        created_at = e.get("created_at", "UNKNOWN")
        # Convert timestamp to readable format
        if isinstance(created_at, (int, float)):
            created_at = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(created_at))

        # Get file path from edge data
        file_path = e.get("file_path", "unknown_source")

        relations_context.append(
            {
                "id": i + 1,
                "entity1": e["src_id"],
                "entity2": e["tgt_id"],
                "description": e["description"],
                "keywords": e["keywords"],
                "weight": e["weight"],
                "rank": e["rank"],
                "connectivity": e.get("connectivity", 0),
                "created_at": created_at,
                "file_path": file_path,
            }
        )

    entities_context = []
    for i, n in enumerate(use_entities):
        created_at = n.get("created_at", "UNKNOWN")
        # Convert timestamp to readable format
        if isinstance(created_at, (int, float)):
            created_at = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(created_at))

        # Get file path from node data
        file_path = n.get("file_path", "unknown_source")

        desc = n.get("description", "UNKNOWN")
        if n.get("additional_properties"):
            desc += f"\n{n['additional_properties']}"
        if n.get("entity_community"):
            desc += f"\n{n['entity_community']}"

        entities_context.append(
            {
                "id": i + 1,
                "entity": n["entity_name"],
                "type": n.get("entity_type", "UNKNOWN"),
                "description": desc,
                "rank": n["rank"],
                "created_at": created_at,
                "file_path": file_path,
            }
        )

    text_units_context = []
    for i, t in enumerate(use_text_units):
        text_units_context.append(
            {
                "id": i + 1,
                "content": t["content"],
                "file_path": t.get("file_path", "unknown"),
            }
        )
    return entities_context, relations_context, text_units_context


async def _find_most_related_entities_from_relationships(
    edge_datas: list[dict],
    query_param: QueryParam,
    knowledge_graph_inst: BaseGraphStorage,
):
    entity_names = []
    seen = set()

    for e in edge_datas:
        if e["src_id"] not in seen:
            entity_names.append(e["src_id"])
            seen.add(e["src_id"])
        if e["tgt_id"] not in seen:
            entity_names.append(e["tgt_id"])
            seen.add(e["tgt_id"])

    # Batch approach: Retrieve nodes and their degrees concurrently with one query each.
    nodes_dict, degrees_dict = await asyncio.gather(
        knowledge_graph_inst.get_nodes_batch(entity_names),
        knowledge_graph_inst.node_degrees_batch(entity_names),
    )

    # Rebuild the list in the same order as entity_names
    node_datas = []
    for entity_name in entity_names:
        node = nodes_dict.get(entity_name)
        degree = degrees_dict.get(entity_name, 0)
        if node is None:
            logger.warning(f"Node '{entity_name}' not found in batch retrieval.")
            continue
        # Combine the node data with the entity name and computed degree (as rank)
        combined = {**node, "entity_name": entity_name, "rank": degree}
        node_datas.append(combined)

    tokenizer: Tokenizer = knowledge_graph_inst.global_config.get("tokenizer")
    len_node_datas = len(node_datas)
    node_datas = truncate_list_by_token_size(
        node_datas,
        key=lambda x: x.get("description") or "",
        max_token_size=query_param.max_token_for_local_context,
        tokenizer=tokenizer,
    )
    logger.debug(
        f"Truncate entities from {len_node_datas} to {len(node_datas)} (max tokens:{query_param.max_token_for_local_context})"
    )

    return node_datas


async def _find_related_text_unit_from_relationships(
    edge_datas: list[dict],
    query_param: QueryParam,
    text_chunks_db: BaseKVStorage,
    knowledge_graph_inst: BaseGraphStorage,
):
    text_units = []
    for dp in edge_datas:
        source_id = dp.get("source_id")
        if source_id is not None:
            text_units.append(
                split_string_by_multi_markers(source_id, [GRAPH_FIELD_SEP])
            )
    all_text_units_lookup = {}
    semaphore = asyncio.Semaphore(CHUNK_FETCH_MAX_CONCURRENCY)

    async def fetch_chunk_data(c_id, index):
        if c_id in all_text_units_lookup:
            return
        async with semaphore:
            chunk_data = await text_chunks_db.get_by_id(c_id)
            if chunk_data is not None and "content" in chunk_data:
                all_text_units_lookup[c_id] = {
                    "data": chunk_data,
                    "order": index,
                }

    tasks = []
    for index, unit_list in enumerate(text_units):
        for c_id in unit_list:
            tasks.append(fetch_chunk_data(c_id, index))

    await asyncio.gather(*tasks)

    if not all_text_units_lookup:
        logger.warning("No valid text chunks found")
        return []

    all_text_units = [{"id": k, **v} for k, v in all_text_units_lookup.items()]
    all_text_units = sorted(all_text_units, key=lambda x: x["order"])

    # Ensure all text chunks have content
    valid_text_units = [
        t for t in all_text_units if t["data"] is not None and "content" in t["data"]
    ]

    if not valid_text_units:
        logger.warning("No valid text chunks after filtering")
        return []

    tokenizer: Tokenizer = text_chunks_db.global_config.get("tokenizer")
    truncated_text_units = truncate_list_by_token_size(
        valid_text_units,
        key=lambda x: x["data"]["content"],
        max_token_size=query_param.max_token_for_text_unit,
        tokenizer=tokenizer,
    )

    logger.debug(
        f"Truncate chunks from {len(valid_text_units)} to {len(truncated_text_units)} (max tokens:{query_param.max_token_for_text_unit})"
    )

    all_text_units: list[TextChunkSchema] = [t["data"] for t in truncated_text_units]

    return all_text_units


async def _collect_multi_hop_paths(
    entities_context: list[dict],
    knowledge_graph_inst: BaseGraphStorage,
    top_k: int = 5,
    hashing_kv: BaseKVStorage | None = None,
    min_strength: float = 0.0,
    keywords: list[str] | None = None,
) -> list[dict]:
    """Collect multi-hop paths for entities with optional caching and ranking."""

    paths: list[dict] = []
    keywords = [k.lower() for k in keywords] if keywords else []

    for ent in entities_context[:top_k]:
        ent_name = ent.get("entity") or ent.get("entity_name")
        if not ent_name:
            continue

        cache_key = compute_args_hash(
            ent_name,
            str(top_k),
            str(min_strength),
            "-".join(sorted(keywords)) if keywords else "",
            cache_type="multi_hop",
        )
        cached, _, _, _ = await handle_cache(
            hashing_kv, cache_key, ent_name, mode="multi_hop", cache_type="multi_hop"
        )
        if cached is not None:
            try:
                res = json.loads(cached)
            except Exception:
                res = []
        else:
            try:
                res = await knowledge_graph_inst.multi_hop_paths(
                    ent_name, max_depth=3, top_k=top_k
                )
            except Exception as e:
                logger.warning(f"multi_hop retrieval failed for {ent_name}: {e}")
                continue
            if hashing_kv is not None:
                await save_to_cache(
                    hashing_kv,
                    CacheData(
                        args_hash=cache_key,
                        content=json.dumps(res, ensure_ascii=False),
                        prompt=ent_name,
                        mode="multi_hop",
                        cache_type="multi_hop",
                    ),
                )

        for p in res:
            if p.get("path_strength", 0) >= min_strength:
                paths.append(p)

    def rank_key(p: dict) -> float:
        score = p.get("path_strength", 0)
        if keywords and p.get("path_keywords"):
            kw_set = set(k.strip().lower() for k in p["path_keywords"].split(","))
            overlap = len(set(keywords) & kw_set)
            score += overlap * 0.1
        return score

    paths.sort(key=rank_key, reverse=True)
    return paths[:top_k]


async def naive_query(
    query: str,
    chunks_vdb: BaseVectorStorage,
    query_param: QueryParam,
    global_config: dict[str, str],
    hashing_kv: BaseKVStorage | None = None,
    system_prompt: str | None = None,
) -> str | AsyncIterator[str]:
    if query_param.model_func:
        use_model_func = query_param.model_func
    else:
        use_model_func = global_config["llm_model_func"]
        # Apply higher priority (5) to query relation LLM function
        use_model_func = partial(use_model_func, _priority=5)

    # Handle cache
    args_hash = compute_args_hash(query_param.mode, query, cache_type="query")
    cached_response, quantized, min_val, max_val = await handle_cache(
        hashing_kv, args_hash, query, query_param.mode, cache_type="query"
    )
    if cached_response is not None:
        return cached_response

    tokenizer: Tokenizer = global_config["tokenizer"]

    _, _, text_units_context = await _get_vector_context(
        query,
        chunks_vdb,
        query_param,
        tokenizer,
        global_config,
        hashing_kv,
    )

    if text_units_context is None or len(text_units_context) == 0:
        return PROMPTS["fail_response"]

    text_units_str = json.dumps(text_units_context, ensure_ascii=False)
    if query_param.only_need_context:
        return f"""
---Document Chunks---

```json
{text_units_str}
```

"""
    # Process conversation history
    history_context = ""
    if query_param.conversation_history:
        history_context = get_conversation_turns(
            query_param.conversation_history, query_param.history_turns
        )

    # Build system prompt
    user_prompt = (
        query_param.user_prompt
        if query_param.user_prompt
        else PROMPTS["DEFAULT_USER_PROMPT"]
    )
    sys_prompt_temp = system_prompt if system_prompt else PROMPTS["naive_rag_response"]
    sys_prompt = sys_prompt_temp.format(
        content_data=text_units_str,
        response_type=query_param.response_type,
        history=history_context,
        user_prompt=user_prompt,
        user_profile=json.dumps(query_param.user_profile, ensure_ascii=False),
    )

    if query_param.only_need_prompt:
        return sys_prompt

    len_of_prompts = len(tokenizer.encode(query + sys_prompt))
    logger.debug(f"[naive_query]Prompt Tokens: {len_of_prompts}")

    response = await use_model_func(
        query,
        system_prompt=sys_prompt,
        stream=query_param.stream,
    )

    if isinstance(response, str) and len(response) > len(sys_prompt):
        response = (
            response[len(sys_prompt) :]
            .replace(sys_prompt, "")
            .replace("user", "")
            .replace("model", "")
            .replace(query, "")
            .replace("<system>", "")
            .replace("</system>", "")
            .strip()
        )

    if hashing_kv.global_config.get("enable_llm_cache"):
        # Save to cache
        await save_to_cache(
            hashing_kv,
            CacheData(
                args_hash=args_hash,
                content=response,
                prompt=query,
                quantized=quantized,
                min_val=min_val,
                max_val=max_val,
                mode=query_param.mode,
                cache_type="query",
            ),
        )

    return response


# TODO: Deprecated, use user_prompt in QueryParam instead
async def kg_query_with_keywords(
    query: str,
    knowledge_graph_inst: BaseGraphStorage,
    entities_vdb: BaseVectorStorage,
    relationships_vdb: BaseVectorStorage,
    text_chunks_db: BaseKVStorage,
    query_param: QueryParam,
    global_config: dict[str, str],
    hashing_kv: BaseKVStorage | None = None,
    ll_keywords: list[str] = [],
    hl_keywords: list[str] = [],
    community: str = "",
    chunks_vdb: BaseVectorStorage | None = None,
) -> str | AsyncIterator[str]:
    """
    Refactored kg_query that does NOT extract keywords by itself.
    It expects hl_keywords and ll_keywords to be set in query_param, or defaults to empty.
    Then it uses those to build context and produce a final LLM response.
    """
    if query_param.model_func:
        use_model_func = query_param.model_func
    else:
        use_model_func = global_config["llm_model_func"]
        # Apply higher priority (5) to query relation LLM function
        use_model_func = partial(use_model_func, _priority=5)

    args_hash = compute_args_hash(query_param.mode, query, cache_type="query")
    cached_response, quantized, min_val, max_val = await handle_cache(
        hashing_kv, args_hash, query, query_param.mode, cache_type="query"
    )
    if cached_response is not None:
        return cached_response

    # If neither has any keywords, you could handle that logic here.
    if not hl_keywords and not ll_keywords:
        logger.warning(
            "No keywords found in query_param. Could default to global mode or fail."
        )
        return PROMPTS["fail_response"]
    if not ll_keywords and query_param.mode in ["local", "hybrid"]:
        logger.warning("low_level_keywords is empty, switching to global mode.")
        query_param.mode = "global"
    if not hl_keywords and query_param.mode in ["global", "hybrid"]:
        logger.warning("high_level_keywords is empty, switching to local mode.")
        query_param.mode = "local"

    ll_keywords_str = ", ".join(ll_keywords) if ll_keywords else ""
    hl_keywords_str = ", ".join(hl_keywords) if hl_keywords else ""
    community_str = community if community else ""

    context = await _build_query_context(
        ll_keywords_str,
        hl_keywords_str,
        community_str,
        knowledge_graph_inst,
        entities_vdb,
        relationships_vdb,
        text_chunks_db,
        query_param,
        chunks_vdb=chunks_vdb,
        global_config=global_config,
        hashing_kv=hashing_kv,
    )
    if not context:
        return PROMPTS["fail_response"]

    if query_param.only_need_context:
        return context

    # Process conversation history
    history_context = ""
    if query_param.conversation_history:
        history_context = get_conversation_turns(
            query_param.conversation_history, query_param.history_turns
        )

    sys_prompt_temp = PROMPTS["rag_response"]
    sys_prompt = sys_prompt_temp.format(
        context_data=context,
        response_type=query_param.response_type,
        history=history_context,
        user_profile=json.dumps(query_param.user_profile, ensure_ascii=False),
    )

    if query_param.only_need_prompt:
        return sys_prompt

    tokenizer: Tokenizer = global_config["tokenizer"]
    len_of_prompts = len(tokenizer.encode(query + sys_prompt))
    logger.debug(f"[kg_query_with_keywords]Prompt Tokens: {len_of_prompts}")

    # 6. Generate response
    response = await use_model_func(
        query,
        system_prompt=sys_prompt,
        stream=query_param.stream,
    )

    # Clean up response content
    if isinstance(response, str) and len(response) > len(sys_prompt):
        response = (
            response.replace(sys_prompt, "")
            .replace("user", "")
            .replace("model", "")
            .replace(query, "")
            .replace("<system>", "")
            .replace("</system>", "")
            .strip()
        )

        if hashing_kv.global_config.get("enable_llm_cache"):
            await save_to_cache(
                hashing_kv,
                CacheData(
                    args_hash=args_hash,
                    content=response,
                    prompt=query,
                    quantized=quantized,
                    min_val=min_val,
                    max_val=max_val,
                    mode=query_param.mode,
                    cache_type="query",
                ),
            )

    return response


# TODO: Deprecated, use user_prompt in QueryParam instead
async def query_with_keywords(
    query: str,
    prompt: str,
    param: QueryParam,
    knowledge_graph_inst: BaseGraphStorage,
    entities_vdb: BaseVectorStorage,
    relationships_vdb: BaseVectorStorage,
    chunks_vdb: BaseVectorStorage,
    text_chunks_db: BaseKVStorage,
    global_config: dict[str, str],
    hashing_kv: BaseKVStorage | None = None,
) -> str | AsyncIterator[str]:
    """
    Extract keywords from the query and then use them for retrieving information.

    1. Extracts high-level and low-level keywords from the query
    2. Formats the query with the extracted keywords and prompt
    3. Uses the appropriate query method based on param.mode

    Args:
        query: The user's query
        prompt: Additional prompt to prepend to the query
        param: Query parameters
        knowledge_graph_inst: Knowledge graph storage
        entities_vdb: Entities vector database
        relationships_vdb: Relationships vector database
        chunks_vdb: Document chunks vector database
        text_chunks_db: Text chunks storage
        global_config: Global configuration
        hashing_kv: Cache storage

    Returns:
        Query response or async iterator
    """
    # Extract keywords
    hl_keywords, ll_keywords, community = await get_keywords_from_query(
        query=query,
        query_param=param,
        global_config=global_config,
        hashing_kv=hashing_kv,
    )

    # Create a new string with the prompt and the keywords
    keywords_str = ", ".join(
        ll_keywords + hl_keywords + ([community] if community else [])
    )
    formatted_question = (
        f"{prompt}\n\n### Keywords\n\n{keywords_str}\n\n### Query\n\n{query}"
    )

    param.original_query = query

    # Use appropriate query method based on mode
    if param.mode in ["local", "global", "hybrid", "mix"]:
        return await kg_query_with_keywords(
            formatted_question,
            knowledge_graph_inst,
            entities_vdb,
            relationships_vdb,
            text_chunks_db,
            param,
            global_config,
            hashing_kv=hashing_kv,
            hl_keywords=hl_keywords,
            ll_keywords=ll_keywords,
            community=community,
            chunks_vdb=chunks_vdb,
        )
    elif param.mode == "naive":
        return await naive_query(
            formatted_question,
            chunks_vdb,
            text_chunks_db,
            param,
            global_config,
            hashing_kv=hashing_kv,
        )
    else:
        raise ValueError(f"Unknown mode {param.mode}")
