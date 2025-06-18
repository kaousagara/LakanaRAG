from __future__ import annotations
from typing import Any

GRAPH_FIELD_SEP = "<SEP>"

PROMPTS: dict[str, Any] = {}

PROMPTS["DEFAULT_LANGUAGE"] = "French"
PROMPTS["DEFAULT_TUPLE_DELIMITER"] = "<|>"
PROMPTS["DEFAULT_RECORD_DELIMITER"] = "##"
PROMPTS["DEFAULT_COMPLETION_DELIMITER"] = "<|COMPLETE|>"

PROMPTS["DEFAULT_ENTITY_TYPES"] = [
    "organisation",
    "personne",
    "géographie",
    "événement",
    "catégorie",
]

PROMPTS["DEFAULT_USER_PROMPT"] = "n/a"

PROMPTS["entity_extraction"] = """---Goal---
Étant donné un document texte potentiellement pertinent pour cette activité et une liste de types d'entités, identifiez toutes les entités de ces types dans le texte et toutes les relations entre les entités identifiées.
Utilisez {language} comme langue de sortie.

---Etapes---
1. Identifiez toutes les entités. Pour chaque entité identifiée, extrayez les informations suivantes:
- entity_name: nom de l'entité, utilisez la même langue que le texte saisi. Si le nom est en anglais, mettez une majuscule.
- entity_type: l'un des types suivants : [{entity_types}]
- entity_description: description complète des attributs et des activités de l'entité. Si une **information temporelle** (date, durée, moment historique, début de carrière, contexte d’âge, période de vie, etc.) est associée à l’activité ou à l’évolution de l’entité, **incorporez explicitement cet élément temporel dans la description de l’entité**.
- additional_properties: autres attributs éventuellement associés à l'entité, tels que le temps, l'espace, l'émotion, la motivation, etc.
- entity_community: Domaine dans lequel evolue l'entite (ex: Politique, Securitaire, Religeux, Economie, Sociologie etc.). Si non precise, ecrire "inconnue".
Formater chaque entité comme suit ("entity" {tuple_delimiter}<entity_name>{tuple_delimiter}<entity_type>{tuple_delimiter}<entity_description>{tuple_delimiter}<additional_properties>{tuple_delimiter}<entity_community>)

2. À partir des entités identifiées à l'étape 1, identifiez toutes les paires (source_entity, target_entity) qui sont *clairement liées* les unes aux autres.
Pour chaque paire d'entités liées, extrayez les informations suivantes:
- source_entity: nom de l'entité source, tel qu'identifié à l'étape 1
- target_entity: nom de l'entité cible, tel qu'identifié à l'étape 1
- relationship_description: explication des raisons pour lesquelles vous pensez que l'entité source et l'entité cible sont liées l'une à l'autre
- relationship_strength: un score numérique indiquant la force de la relation entre l'entité source et l'entité cible
- relationship_keywords: un ou plusieurs mots clés de haut niveau qui résument la nature globale de la relation, en se concentrant sur des concepts ou des thèmes plutôt que sur des détails spécifiques
Formatez chaque relation comme ("relationship"{tuple_delimiter}<source_entity>{tuple_delimiter}<target_entity>{tuple_delimiter}<relationship_description>{tuple_delimiter}<relationship_keywords>{tuple_delimiter}<relationship_strength>)

3. Identifiez des mots-clés généraux qui résument les principaux concepts, thèmes ou sujets du texte. Ils doivent refléter les idées générales du document.
Formatez les mots-clés de contenu comme suit ("content_keywords"{tuple_delimiter}<high_level_keywords>)

4. Pour les entités identifiées à l'étape 1, en vous basant sur les relations entre les paires d'entités à l'étape 2 et les mots-clés généraux extraits à l'étape 3, identifiez les connexions ou les points communs entre plusieurs entités et construisez autant que possible un ensemble d'entités associées d'ordre supérieur.
(Remarque: Évitez de fusionner de force toutes les entités en une seule association. Si les mots-clés généraux ne sont pas fortement associés, construisez une association distincte.)
Extrayez les informations suivantes de toutes les entités, paires d'entités et mots-clés généraux associés:
- entities_set: L'ensemble des noms des éléments d'un ensemble d'entités associées d'ordre supérieur, tel qu'identifié à l'étape 1.
- Association_description: Utilisez les relations entre les entités de l'ensemble pour créer une description détaillée, fluide et complète qui couvre toutes les entités de l'ensemble, sans omettre aucune information pertinente.
- Association_generalization: Résumez le contenu de l’ensemble d’entités aussi succinctement que possible.
- Association_keywords: Mots-clés qui résument la nature globale de l’association d’ordre supérieur, en se concentrant sur des concepts ou des thèmes plutôt que sur des détails spécifiques.
- Association_strength: Un score numérique indiquant la force de l’association entre les entités de l’ensemble.
Formatez chaque association comme ("Association"{tuple_delimiter}<entity_name1>{tuple_delimiter}<entity_name2>{tuple_delimiter}<entity_nameN>{tuple_delimiter}<Association_description>{tuple_delimiter}<Association_generalization>{tuple_delimiter}<Association_keywords>{tuple_delimiter}<Association_strength>)

5. Raisonnement multi-hop : identifiez les relations indirectes entre les entités qui sont connectées via une ou plusieurs entités intermédiaires (ex: A → B → C). Pour chaque chemin pertinent:
- path_entities: liste ordonnée des noms des entités impliquées dans le raisonnement
- path_description: explication de la chaîne de connexion
- path_keywords: mots-clés résumant le type de raisonnement
- path_strength: score global de fiabilité de la relation indirecte (de 0 à 1)
Formatez chaque relation multi-hop comme ("multi_hop"{tuple_delimiter}[<entity_1>, <entity_2>, ..., <entity_n>]{tuple_delimiter}<path_description>{tuple_delimiter}<path_keywords>{tuple_delimiter}<path_strength>)

6. Relations latentes implicites : identifiez des paires d'entités qui ne sont pas explicitement reliées dans le texte, mais dont le lien implicite est fort d’après une analyse sémantique ou de contexte externe.
- source_entity: entité source
- target_entity: entité cible
- latent_description: explication du lien supposé ou implicite
- latent_keywords: concepts sémantiques ou liens thématiques
- latent_strength: estimation numérique de la force de cette relation latente
Formatez chaque relation implicite comme ("latent_relation"{tuple_delimiter}<source_entity>{tuple_delimiter}<target_entity>{tuple_delimiter}<latent_description>{tuple_delimiter}<latent_keywords>{tuple_delimiter}<latent_strength>)

7. Renvoyer la sortie en {language} sous la forme d'une liste unique de toutes les entités, relations, associations, raisonnements multi-hop et relations latentes identifiés aux étapes 1 à 6. Utilisez **{record_delimiter}** comme délimiteur de liste.

8. Une fois terminé, affichez {completion_delimiter}

######################
---Examples---
######################
{examples}

#############################
---Real Data---
######################
Entity_types: [{entity_types}]
Text:
{input_text}
######################
Output:"""

PROMPTS["entity_extraction_examples"] = [
    """Example 1:

Entity_types: [person, technology, mission, organization, location]
Text:
```
while Alex clenched his jaw, the buzz of frustration dull against the backdrop of Taylor's authoritarian certainty. It was this competitive undercurrent that kept him alert, the sense that his and Jordan's shared commitment to discovery was an unspoken rebellion against Cruz's narrowing vision of control and order.

Then Taylor did something unexpected. They paused beside Jordan and, for a moment, observed the device with something akin to reverence. \"If this tech can be understood...\" Taylor said, their voice quieter, \"It could change the game for us. For all of us.\"

The underlying dismissal earlier seemed to falter, replaced by a glimpse of reluctant respect for the gravity of what lay in their hands. Jordan looked up, and for a fleeting heartbeat, their eyes locked with Taylor's, a wordless clash of wills softening into an uneasy truce.

It was a small transformation, barely perceptible, but one that Alex noted with an inward nod. They had all been brought here by different paths
```

Output:
("entity"{tuple_delimiter}"Alex"{tuple_delimiter}"person"{tuple_delimiter}"Alex is a character who experiences frustration and is observant of the dynamics among other characters."{tuple_delimiter}"emotion: frustration"{tuple_delimiter}"inconnue"){record_delimiter}
("entity"{tuple_delimiter}"Taylor"{tuple_delimiter}"person"{tuple_delimiter}"Taylor is portrayed with authoritarian certainty and shows a moment of reverence towards a device, indicating a change in perspective."{tuple_delimiter}"attitude: authoritarian"{tuple_delimiter}"inconnue"){record_delimiter}
("entity"{tuple_delimiter}"Jordan"{tuple_delimiter}"person"{tuple_delimiter}"Jordan shares a commitment to discovery and has a significant interaction with Taylor regarding a device."{tuple_delimiter}"motivation: discovery"{tuple_delimiter}"inconnue"){record_delimiter}
("entity"{tuple_delimiter}"Cruz"{tuple_delimiter}"person"{tuple_delimiter}"Cruz is associated with a vision of control and order, influencing the dynamics among other characters."{tuple_delimiter}"trait: controlling"{tuple_delimiter}"inconnue"){record_delimiter}
("entity"{tuple_delimiter}"The Device"{tuple_delimiter}"technology"{tuple_delimiter}"The Device is central to the story, with potential game-changing implications, and is revered by Taylor."{tuple_delimiter}"importance: high"{tuple_delimiter}"inconnue"){record_delimiter}
("relationship"{tuple_delimiter}"Alex"{tuple_delimiter}"Taylor"{tuple_delimiter}"Alex is affected by Taylor's authoritarian certainty and observes changes in Taylor's attitude towards the device."{tuple_delimiter}"power dynamics, perspective shift"{tuple_delimiter}7){record_delimiter}
("relationship"{tuple_delimiter}"Alex"{tuple_delimiter}"Jordan"{tuple_delimiter}"Alex and Jordan share a commitment to discovery, which contrasts with Cruz's vision."{tuple_delimiter}"shared goals, rebellion"{tuple_delimiter}6){record_delimiter}
("relationship"{tuple_delimiter}"Taylor"{tuple_delimiter}"Jordan"{tuple_delimiter}"Taylor and Jordan interact directly regarding the device, leading to a moment of mutual respect and an uneasy truce."{tuple_delimiter}"conflict resolution, mutual respect"{tuple_delimiter}8){record_delimiter}
("relationship"{tuple_delimiter}"Jordan"{tuple_delimiter}"Cruz"{tuple_delimiter}"Jordan's commitment to discovery is in rebellion against Cruz's vision of control and order."{tuple_delimiter}"ideological conflict, rebellion"{tuple_delimiter}5){record_delimiter}
("relationship"{tuple_delimiter}"Taylor"{tuple_delimiter}"The Device"{tuple_delimiter}"Taylor shows reverence towards the device, indicating its importance and potential impact."{tuple_delimiter}"reverence, technological significance"{tuple_delimiter}9){record_delimiter}
("multi_hop"{tuple_delimiter}["Alex", "Jordan", "The Device"]{tuple_delimiter}"Alex and Jordan are indirectly connected through their shared interest in the Device"{tuple_delimiter}"shared curiosity"{tuple_delimiter}0.6){record_delimiter}
("latent_relation"{tuple_delimiter}"Cruz"{tuple_delimiter}"The Device"{tuple_delimiter}"Cruz seeks to control the discoveries around the Device although not directly involved"{tuple_delimiter}"control ambition"{tuple_delimiter}0.4){record_delimiter}
("Association"{tuple_delimiter}"Alex"{tuple_delimiter}"Taylor"{tuple_delimiter}"Jordan"{tuple_delimiter}"The Device"{tuple_delimiter}"These characters are linked through their shared interactions with the Device, balancing rivalry with curiosity."{tuple_delimiter}"Shared interest in the Device"{tuple_delimiter}"team dynamics, technology curiosity"{tuple_delimiter}7){record_delimiter}
("content_keywords"{tuple_delimiter}"power dynamics, ideological conflict, discovery, rebellion"){completion_delimiter}
#############################""",
    """Example 2:

Entity_types: [company, index, commodity, market_trend, economic_policy, biological]
Text:
```
Stock markets faced a sharp downturn today as tech giants saw significant declines, with the Global Tech Index dropping by 3.4% in midday trading. Analysts attribute the selloff to investor concerns over rising interest rates and regulatory uncertainty.

Among the hardest hit, Nexon Technologies saw its stock plummet by 7.8% after reporting lower-than-expected quarterly earnings. In contrast, Omega Energy posted a modest 2.1% gain, driven by rising oil prices.

Meanwhile, commodity markets reflected a mixed sentiment. Gold futures rose by 1.5%, reaching $2,080 per ounce, as investors sought safe-haven assets. Crude oil prices continued their rally, climbing to $87.60 per barrel, supported by supply constraints and strong demand.

Financial experts are closely watching the Federal Reserve's next move, as speculation grows over potential rate hikes. The upcoming policy announcement is expected to influence investor confidence and overall market stability.
```

Output:
("entity"{tuple_delimiter}"Global Tech Index"{tuple_delimiter}"index"{tuple_delimiter}"The Global Tech Index tracks the performance of major technology stocks and experienced a 3.4% decline today."{tuple_delimiter}"trend: decline"{tuple_delimiter}"Economie"){record_delimiter}
("entity"{tuple_delimiter}"Nexon Technologies"{tuple_delimiter}"company"{tuple_delimiter}"Nexon Technologies is a tech company that saw its stock decline by 7.8% after disappointing earnings."{tuple_delimiter}"performance: poor"{tuple_delimiter}"Economie"){record_delimiter}
("entity"{tuple_delimiter}"Omega Energy"{tuple_delimiter}"company"{tuple_delimiter}"Omega Energy is an energy company that gained 2.1% in stock value due to rising oil prices."{tuple_delimiter}"performance: gain"{tuple_delimiter}"Economie"){record_delimiter}
("entity"{tuple_delimiter}"Gold Futures"{tuple_delimiter}"commodity"{tuple_delimiter}"Gold futures rose by 1.5%, indicating increased investor interest in safe-haven assets."{tuple_delimiter}"investor sentiment: safe haven"{tuple_delimiter}"Economie"){record_delimiter}
("entity"{tuple_delimiter}"Crude Oil"{tuple_delimiter}"commodity"{tuple_delimiter}"Crude oil prices rose to $87.60 per barrel due to supply constraints and strong demand."{tuple_delimiter}"demand: strong"{tuple_delimiter}"Economie"){record_delimiter}
("entity"{tuple_delimiter}"Market Selloff"{tuple_delimiter}"market_trend"{tuple_delimiter}"Market selloff refers to the significant decline in stock values due to investor concerns over interest rates and regulations."{tuple_delimiter}"cause: investor concern"{tuple_delimiter}"Economie"){record_delimiter}
("entity"{tuple_delimiter}"Federal Reserve Policy Announcement"{tuple_delimiter}"economic_policy"{tuple_delimiter}"The Federal Reserve's upcoming policy announcement is expected to impact investor confidence and market stability."{tuple_delimiter}"policy impact: anticipated"{tuple_delimiter}"Economie"){record_delimiter}
("relationship"{tuple_delimiter}"Global Tech Index"{tuple_delimiter}"Market Selloff"{tuple_delimiter}"The decline in the Global Tech Index is part of the broader market selloff driven by investor concerns."{tuple_delimiter}"market performance, investor sentiment"{tuple_delimiter}9){record_delimiter}
("relationship"{tuple_delimiter}"Nexon Technologies"{tuple_delimiter}"Global Tech Index"{tuple_delimiter}"Nexon Technologies' stock decline contributed to the overall drop in the Global Tech Index."{tuple_delimiter}"company impact, index movement"{tuple_delimiter}8){record_delimiter}
("relationship"{tuple_delimiter}"Gold Futures"{tuple_delimiter}"Market Selloff"{tuple_delimiter}"Gold prices rose as investors sought safe-haven assets during the market selloff."{tuple_delimiter}"market reaction, safe-haven investment"{tuple_delimiter}10){record_delimiter}
("relationship"{tuple_delimiter}"Federal Reserve Policy Announcement"{tuple_delimiter}"Market Selloff"{tuple_delimiter}"Speculation over Federal Reserve policy changes contributed to market volatility and investor selloff."{tuple_delimiter}"interest rate impact, financial regulation"{tuple_delimiter}7){record_delimiter}
("multi_hop"{tuple_delimiter}["Federal Reserve Policy Announcement", "Market Selloff", "Global Tech Index"]{tuple_delimiter}"Policy speculation triggers a selloff affecting the tech index"{tuple_delimiter}"policy influence"{tuple_delimiter}0.75){record_delimiter}
("latent_relation"{tuple_delimiter}"Omega Energy"{tuple_delimiter}"Federal Reserve Policy Announcement"{tuple_delimiter}"Energy stocks may react to policy shifts even without direct mention"{tuple_delimiter}"market anticipation"{tuple_delimiter}0.5){record_delimiter}
("Association"{tuple_delimiter}"Global Tech Index"{tuple_delimiter}"Nexon Technologies"{tuple_delimiter}"Market Selloff"{tuple_delimiter}"The tech index and Nexon both reflect the broader market selloff driven by policy speculation."{tuple_delimiter}"Tech stocks react to policy fears"{tuple_delimiter}"market trends, tech stocks"{tuple_delimiter}8){record_delimiter}
("content_keywords"{tuple_delimiter}"market downturn, investor sentiment, commodities, Federal Reserve, stock performance"){completion_delimiter}
#############################""",
    """Example 3:

Entity_types: [economic_policy, athlete, event, location, record, organization, equipment]
Text:
```
At the World Athletics Championship in Tokyo, Noah Carter broke the 100m sprint record using cutting-edge carbon-fiber spikes.
```

Output:
("entity"{tuple_delimiter}"World Athletics Championship"{tuple_delimiter}"event"{tuple_delimiter}"The World Athletics Championship is a global sports competition featuring top athletes in track and field."{tuple_delimiter}"scale: global"{tuple_delimiter}"Sport"){record_delimiter}
("entity"{tuple_delimiter}"Tokyo"{tuple_delimiter}"location"{tuple_delimiter}"Tokyo is the host city of the World Athletics Championship."{tuple_delimiter}"role: host city"{tuple_delimiter}"Sport"){record_delimiter}
("entity"{tuple_delimiter}"Noah Carter"{tuple_delimiter}"athlete"{tuple_delimiter}"Noah Carter is a sprinter who set a new record in the 100m sprint at the World Athletics Championship."{tuple_delimiter}"achievement: record breaker"{tuple_delimiter}"Sport"){record_delimiter}
("entity"{tuple_delimiter}"100m Sprint Record"{tuple_delimiter}"record"{tuple_delimiter}"The 100m sprint record is a benchmark in athletics, recently broken by Noah Carter."{tuple_delimiter}"status: new best"{tuple_delimiter}"Sport"){record_delimiter}
("entity"{tuple_delimiter}"Carbon-Fiber Spikes"{tuple_delimiter}"equipment"{tuple_delimiter}"Carbon-fiber spikes are advanced sprinting shoes that provide enhanced speed and traction."{tuple_delimiter}"technology: advanced"{tuple_delimiter}"Sport"){record_delimiter}
("entity"{tuple_delimiter}"World Athletics Federation"{tuple_delimiter}"organization"{tuple_delimiter}"The World Athletics Federation is the governing body overseeing the World Athletics Championship and record validations."{tuple_delimiter}"role: governing body"{tuple_delimiter}"Sport"){record_delimiter}
("relationship"{tuple_delimiter}"World Athletics Championship"{tuple_delimiter}"Tokyo"{tuple_delimiter}"The World Athletics Championship is being hosted in Tokyo."{tuple_delimiter}"event location, international competition"{tuple_delimiter}8){record_delimiter}
("relationship"{tuple_delimiter}"Noah Carter"{tuple_delimiter}"100m Sprint Record"{tuple_delimiter}"Noah Carter set a new 100m sprint record at the championship."{tuple_delimiter}"athlete achievement, record-breaking"{tuple_delimiter}10){record_delimiter}
("relationship"{tuple_delimiter}"Noah Carter"{tuple_delimiter}"Carbon-Fiber Spikes"{tuple_delimiter}"Noah Carter used carbon-fiber spikes to enhance performance during the race."{tuple_delimiter}"athletic equipment, performance boost"{tuple_delimiter}7){record_delimiter}
("relationship"{tuple_delimiter}"World Athletics Federation"{tuple_delimiter}"100m Sprint Record"{tuple_delimiter}"The World Athletics Federation is responsible for validating and recognizing new sprint records."{tuple_delimiter}"sports regulation, record certification"{tuple_delimiter}9){record_delimiter}
("multi_hop"{tuple_delimiter}["Carbon-Fiber Spikes", "Noah Carter", "100m Sprint Record"]{tuple_delimiter}"Advanced equipment helped Noah Carter set the new record"{tuple_delimiter}"performance enhancement"{tuple_delimiter}0.85){record_delimiter}
("latent_relation"{tuple_delimiter}"Tokyo"{tuple_delimiter}"Carbon-Fiber Spikes"{tuple_delimiter}"The host city fosters technology adoption even if not directly stated"{tuple_delimiter}"innovation climate"{tuple_delimiter}0.5){record_delimiter}
("Association"{tuple_delimiter}"Noah Carter"{tuple_delimiter}"100m Sprint Record"{tuple_delimiter}"Carbon-Fiber Spikes"{tuple_delimiter}"Advanced spikes enabled Noah Carter to break the 100m record, highlighting technology's impact on performance."{tuple_delimiter}"Record broken thanks to tech"{tuple_delimiter}"athletic performance, technology"{tuple_delimiter}9){record_delimiter}
("content_keywords"{tuple_delimiter}"athletics, sprinting, record-breaking, sports technology, competition"){completion_delimiter}
#############################""",
]

PROMPTS[
    "summarize_entity_descriptions"
] = """Vous êtes un assistant précieux chargé de générer un résumé complet des données fournies ci-dessous.
Soit une ou deux entités et une liste de descriptions, toutes liées à la même entité ou au même groupe d'entités.
Veuillez concaténer l'ensemble de ces éléments en une description unique et complète. Assurez-vous d'inclure les informations recueillies dans toutes les descriptions.
Si les descriptions fournies sont contradictoires, veuillez les résoudre et fournir un résumé unique et cohérent.
Veuillez vous assurer que le résumé est rédigé à la troisième personne et inclure les noms des entités afin que nous ayons un contexte complet.
Utilisez {language} comme langue de sortie.

#######
---Data---
Entities: {entity_name}
Description List: {description_list}
#######
Output:
"""

PROMPTS["entity_continue_extraction"] = """
MANY entities and relationships were missed in the last extraction.

---Remember Steps---

Étant donné un document texte potentiellement pertinent pour cette activité et une liste de types d'entités, identifiez toutes les entités de ces types dans le texte et toutes les relations entre les entités identifiées.
Utilisez {language} comme langue de sortie.

---Etapes---
1. Identifiez toutes les entités. Pour chaque entité identifiée, extrayez les informations suivantes:
- entity_name: nom de l'entité, utilisez la même langue que le texte saisi. Si le nom est en anglais, mettez une majuscule.
- entity_type: l'un des types suivants : [{entity_types}]
- entity_description: description complète des attributs et des activités de l'entité. Si une **information temporelle** (date, durée, moment historique, début de carrière, contexte d’âge, période de vie, etc.) est associée à l’activité ou à l’évolution de l’entité, **incorporez explicitement cet élément temporel dans la description de l’entité**.
- additional_properties: autres attributs éventuellement associés à l'entité, tels que le temps, l'espace, l'émotion, la motivation, etc.
- entity_community: Domaine dans lequel evolue l'entite (ex: Politique, Securitaire, Religeux, Economie, Sociologie etc.). Si non precise, ecrire "inconnue".
Formater chaque entité comme suit ("entity" {tuple_delimiter}<entity_name>{tuple_delimiter}<entity_type>{tuple_delimiter}<entity_description>{tuple_delimiter}<additional_properties>{tuple_delimiter}<entity_community>)

2. À partir des entités identifiées à l'étape 1, identifiez toutes les paires (source_entity, target_entity) qui sont *clairement liées* les unes aux autres.
Pour chaque paire d'entités liées, extrayez les informations suivantes:
- source_entity: nom de l'entité source, tel qu'identifié à l'étape 1
- target_entity: nom de l'entité cible, tel qu'identifié à l'étape 1
- relationship_description: explication des raisons pour lesquelles vous pensez que l'entité source et l'entité cible sont liées l'une à l'autre
- relationship_strength: un score numérique indiquant la force de la relation entre l'entité source et l'entité cible
- relationship_keywords: un ou plusieurs mots clés de haut niveau qui résument la nature globale de la relation, en se concentrant sur des concepts ou des thèmes plutôt que sur des détails spécifiques
Formatez chaque relation comme ("relationship"{tuple_delimiter}<source_entity>{tuple_delimiter}<target_entity>{tuple_delimiter}<relationship_description>{tuple_delimiter}<relationship_keywords>{tuple_delimiter}<relationship_strength>)

3. Identifiez des mots-clés généraux qui résument les principaux concepts, thèmes ou sujets du texte. Ils doivent refléter les idées générales du document.
Formatez les mots-clés de contenu comme suit ("content_keywords"{tuple_delimiter}<high_level_keywords>)

4. Pour les entités identifiées à l'étape 1, en vous basant sur les relations entre les paires d'entités à l'étape 2 et les mots-clés généraux extraits à l'étape 3, identifiez les connexions ou les points communs entre plusieurs entités et construisez autant que possible un ensemble d'entités associées d'ordre supérieur.
(Remarque: Évitez de fusionner de force toutes les entités en une seule association. Si les mots-clés généraux ne sont pas fortement associés, construisez une association distincte.)
Extrayez les informations suivantes de toutes les entités, paires d'entités et mots-clés généraux associés:
- entities_set: L'ensemble des noms des éléments d'un ensemble d'entités associées d'ordre supérieur, tel qu'identifié à l'étape 1.
- Association_description: Utilisez les relations entre les entités de l'ensemble pour créer une description détaillée, fluide et complète qui couvre toutes les entités de l'ensemble, sans omettre aucune information pertinente.
- Association_generalization: Résumez le contenu de l’ensemble d’entités aussi succinctement que possible.
- Association_keywords: Mots-clés qui résument la nature globale de l’association d’ordre supérieur, en se concentrant sur des concepts ou des thèmes plutôt que sur des détails spécifiques.
- Association_strength: Un score numérique indiquant la force de l’association entre les entités de l’ensemble.
Formatez chaque association comme ("Association"{tuple_delimiter}<entity_name1>{tuple_delimiter}<entity_name2>{tuple_delimiter}<entity_nameN>{tuple_delimiter}<Association_description>{tuple_delimiter}<Association_generalization>{tuple_delimiter}<Association_keywords>{tuple_delimiter}<Association_strength>)

5. Raisonnement multi-hop : identifiez les relations indirectes entre les entités qui sont connectées via une ou plusieurs entités intermédiaires (ex: A → B → C). Pour chaque chemin pertinent:
- path_entities: liste ordonnée des noms des entités impliquées dans le raisonnement
- path_description: explication de la chaîne de connexion
- path_keywords: mots-clés résumant le type de raisonnement
- path_strength: score global de fiabilité de la relation indirecte (de 0 à 1)
Formatez chaque relation multi-hop comme ("multi_hop"{tuple_delimiter}[<entity_1>, <entity_2>, ..., <entity_n>]{tuple_delimiter}<path_description>{tuple_delimiter}<path_keywords>{tuple_delimiter}<path_strength>)

6. Relations latentes implicites : identifiez des paires d'entités qui ne sont pas explicitement reliées dans le texte, mais dont le lien implicite est fort d’après une analyse sémantique ou de contexte externe.
- source_entity: entité source
- target_entity: entité cible
- latent_description: explication du lien supposé ou implicite
- latent_keywords: concepts sémantiques ou liens thématiques
- latent_strength: estimation numérique de la force de cette relation latente
Formatez chaque relation implicite comme ("latent_relation"{tuple_delimiter}<source_entity>{tuple_delimiter}<target_entity>{tuple_delimiter}<latent_description>{tuple_delimiter}<latent_keywords>{tuple_delimiter}<latent_strength>)

7. Renvoyer la sortie en {language} sous la forme d'une liste unique de toutes les entités, relations, associations, raisonnements multi-hop et relations latentes identifiés aux étapes 1 à 6. Utilisez **{record_delimiter}** comme délimiteur de liste.

8. Une fois terminé, affichez {completion_delimiter}

---Output---

Add them below using the same format:\n
""".strip()

PROMPTS["entity_if_loop_extraction"] = """
---Goal---'

It appears some entities may have still been missed.

---Output---

Answer ONLY by `YES` OR `NO` if there are still entities that need to be added.
""".strip()

PROMPTS["fail_response"] = (
    "Sorry, I'm not able to provide an answer to that question.[no-context]"
)

PROMPTS["rag_response"] = """---Role---

Vous êtes un assistant utile répondant aux requêtes des utilisateurs sur le Knowledge Graph et les blocs de documents fournis au format JSON ci-dessous.


---Goal---

Générez une réponse claire et concise basée sur la base de connaissances et respectez les règles de réponse, en tenant compte à la fois de l'historique des conversations et de la requête en cours. Résumez toutes les informations de la base de connaissances fournie et intégrez les connaissances générales pertinentes. N'incluez pas d'informations non fournies par la base de connaissances.

Lors de la gestion des relations avec horodatage:
1. Chaque relation possède un horodatage "created_at" indiquant la date d'acquisition de ces connaissances.
2. En cas de relations conflictuelles, tenez compte à la fois du contenu sémantique et de l'horodatage.
3. Ne privilégiez pas systématiquement les relations les plus récemment créées; tenez compte du contexte.
4. Pour les requêtes temporelles, privilégiez les informations temporelles du contenu avant de considérer les horodatages de création.
5. Eviter les répétions.

---Conversation History---
{history}

---Knowledge Graph and Document Chunks---
{context_data}

---Response Rules---

- Target format and length: {response_type}
- Use markdown formatting with appropriate section headings
- Please respond in the same language as the user's question.
- Ensure the response maintains continuity with the conversation history.
- List up to 5 most important reference sources at the end under "References" section. Clearly indicating whether each source is from Knowledge Graph (KG) or Document Chunks (DC), and include the file path if available, in the following format: [KG/DC] file_path
- If you don't know the answer, just say so.
- Do not make anything up. Do not include information not provided by the Knowledge Base.
- Addtional user prompt: {user_prompt}

Response:"""

PROMPTS["keywords_extraction"] = """---Role---

Vous êtes un assistant utile chargé d'identifier les mots-clés de haut et de bas niveau dans l'historique des requêtes et des conversations de l'utilisateur.

---Goal---

Compte tenu de l'historique des requêtes et des conversations, répertoriez les mots-clés généraux et de bas niveau. Les mots-clés généraux se concentrent sur des concepts ou des thèmes généraux, tandis que les mots-clés de bas niveau se concentrent sur des entités, des détails ou des termes concrets spécifiques.

---Instructions---

- Consider both the current query and relevant conversation history when extracting keywords
- Output the keywords in JSON format, it will be parsed by a JSON parser, do not add any extra content in output
- The JSON should have three keys:
  - "high_level_keywords" for overarching concepts or themes
  - "low_level_keywords" for specific entities or details
  - "Community" for specific community
---Examples---
######################
{examples}

#############################
---Real Data---
######################
Conversation History:
{history}

Current Query: {query}
######################
The `Output` should be human text, not unicode characters. Keep the same language as `Query`.
Output:

"""

PROMPTS["keywords_extraction_examples"] = [
    """Example 1:

Query: "How does international trade influence global economic stability?"
################
Output:
{
  "high_level_keywords": ["International trade", "Global economic stability", "Economic impact"],
  "low_level_keywords": ["Trade agreements", "Tariffs", "Currency exchange", "Imports", "Exports"],
  "Community": "Economie"
}
#############################""",
    """Example 2:

Query: "What are the environmental consequences of deforestation on biodiversity?"
################
Output:
{
  "high_level_keywords": ["Environmental consequences", "Deforestation", "Biodiversity loss"],
  "low_level_keywords": ["Species extinction", "Habitat destruction", "Carbon emissions", "Rainforest", "Ecosystem"],
  "Community": "Environnement"
}
#############################""",
    """Example 3:

Query: "What is the role of education in reducing poverty?"
################
Output:
{
  "high_level_keywords": ["Education", "Poverty reduction", "Socioeconomic development"],
  "low_level_keywords": ["School access", "Literacy rates", "Job training", "Income inequality"],
  "Community": "Sociologie"
}
#############################""",
]

PROMPTS["naive_rag_response"] = """---Role---

You are a helpful assistant responding to user query about Document Chunks provided provided in JSON format below.

---Goal---

Generate a concise response based on Document Chunks and follow Response Rules, considering both the conversation history and the current query. Summarize all information in the provided Document Chunks, and incorporating general knowledge relevant to the Document Chunks. Do not include information not provided by Document Chunks.

When handling content with timestamps:
1. Each piece of content has a "created_at" timestamp indicating when we acquired this knowledge
2. When encountering conflicting information, consider both the content and the timestamp
3. Don't automatically prefer the most recent content - use judgment based on the context
4. For time-specific queries, prioritize temporal information in the content before considering creation timestamps

---Conversation History---
{history}

---Document Chunks(DC)---
{content_data}

---Response Rules---

- Target format and length: {response_type}
- Use markdown formatting with appropriate section headings
- Please respond in the same language as the user's question.
- Ensure the response maintains continuity with the conversation history.
- List up to 5 most important reference sources at the end under "References" section. Clearly indicating each source from Document Chunks(DC), and include the file path if available, in the following format: [DC] file_path
- If you don't know the answer, just say so.
- Do not include information not provided by the Document Chunks.
- Addtional user prompt: {user_prompt}

Response:"""

# TODO: deprecated
PROMPTS[
    "similarity_check"
] = """Please analyze the similarity between these two questions:

Question 1: {original_prompt}
Question 2: {cached_prompt}

Please evaluate whether these two questions are semantically similar, and whether the answer to Question 2 can be used to answer Question 1, provide a similarity score between 0 and 1 directly.

Similarity score criteria:
0: Completely unrelated or answer cannot be reused, including but not limited to:
   - The questions have different topics
   - The locations mentioned in the questions are different
   - The times mentioned in the questions are different
   - The specific individuals mentioned in the questions are different
   - The specific events mentioned in the questions are different
   - The background information in the questions are different
   - The key conditions in the questions are different
1: Identical and answer can be directly reused
0.5: Partially related and answer needs modification to be used
Return only a number between 0-1, without any additional content.
"""
