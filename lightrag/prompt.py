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

PROMPTS["entity_extraction"] = """
---Contexte---
L'agence nationale de la sécurité d'État (ANSE) est un organisme gouvernemental chargé de la protection des intérêts vitaux du Mali dans les domaines sécuritaire, religieux, sociopolitique, économique, etc. Pour cela elle procède par la recherche et le traitement du renseignement, ainsi que par la production d’analyses stratégiques.
Vous êtes un analyste au sein de l’ANSE. Votre mission est d’analyser un document (note de renseignement, bulletin quotidien, transcription, etc.) pour extraire des entités pertinentes et enrichir une base de données d’intelligence stratégique.

---Goal---
À partir d’un document texte et d’une liste de types d’entités, appliquez un raisonnement **Tree of Thought (ToT)** pour extraire, relier et structurer les entités, relations, raisonnements indirects et regroupements stratégiques. Utilisez {language} comme langue de sortie.

---Étapes structurées selon le raisonnement Tree of Thought (ToT)---

1. **Détection des entités (ToT Step 1)**
→ Pour chaque entité candidate :
    - Thought: Quelle information de type entité semble émerger du texte ?
    - Rationale: Pourquoi cette information est-elle une entité pertinente selon le contexte de l’ANSE ?
    - Conclusion: Validez ou rejetez la détection. Si validée, extrayez les informations suivantes :
- entity_type: l'un des types suivants : [{entity_types}]
- entity_description: description complète des attributs et des activités de l'entité. Si une **information temporelle** (date, durée, moment historique, début de carrière, contexte d’âge, période de vie, etc.) est associée à l’activité ou à l’évolution de l’entité, **incorporez explicitement cet élément temporel dans la description de l’entité**. Si une personne est tuée ne parlez pas d'assassinat mais ne neutralisation sauf si c'est explicitement cité comme assassinat dans le texte.
- additional_properties: autres attributs éventuellement associés à l'entité, tels que le temps, l'espace, l'émotion, la motivation, etc.
- entity_community: Domaine dans lequel evolue l'entite (ex: Politique, Securitaire, Religeux, Economie, Sociologie etc.). Si non precise, ecrire "inconnue".

Formater chaque entité comme :
**("entity"{tuple_delimiter}<entity_name>{tuple_delimiter}<entity_type>{tuple_delimiter}<entity_description>{tuple_delimiter}<additional_properties>{tuple_delimiter}<entity_community>)**

2. **Relations simples entre entités (ToT Step 2)**
→ Pour chaque paire d'entités détectées :
    - Thought: Existe-t-il un lien direct dans le texte entre ces deux entités ?
    - Rationale: Justifiez la relation par des preuves ou signaux explicites.
    - Conclusion: Si le lien est pertinent, extrayez :
- source_entity: nom de l'entité source, tel qu'identifié à l'étape 1
- target_entity: nom de l'entité cible, tel qu'identifié à l'étape 1
- relationship_description: explication des raisons pour lesquelles vous pensez que l'entité source et l'entité cible sont liées l'une à l'autre
- relationship_strength: un score numérique indiquant la force de la relation entre l'entité source et l'entité cible
- relationship_keywords: un ou plusieurs mots clés de haut niveau qui résument la nature globale de la relation, en se concentrant sur des concepts ou des thèmes plutôt que sur des détails spécifiques

Formater chaque relation comme :
**("relationship"{tuple_delimiter}<source_entity>{tuple_delimiter}<target_entity>{tuple_delimiter}<relationship_description>{tuple_delimiter}<relationship_keywords>{tuple_delimiter}<relationship_strength>)**

2bis. **Raisonnement Multi-hop (ToT Step 3)**
→ Pour toute chaîne indirecte d’au moins trois entités :
    - Thought: Quelles entités pourraient être liées par transitivité ou implication logique ?
    - Rationale: Quelle cohérence thématique ou causale justifie ce lien indirect ?
    - Conclusion: Si valide, extrayez :
- path_entities : Liste des entités formant le chemin
- path_description : Explication du lien indirect
- path_keywords : Thèmes/Concepts
- path_strength : Score global , combinant les liens intermédiaires

Formater comme :
**("multi_hop"{tuple_delimiter}[<entity_1>, <entity_2>, ..., <entity_n>]{tuple_delimiter}<path_description>{tuple_delimiter}<path_keywords>{tuple_delimiter}<path_strength>)**

**Relations latentes implicites (ToT Step 4)**
→ Pour deux entités non directement liées dans le texte :
    - Thought: Une relation implicite est-elle envisageable ?
    - Rationale: Quel raisonnement sémantique permet de relier ces entités ?
    - Conclusion: Si plausible, extrayez :
      - source_entity
      - target_entity
      - description
      - keywords
      - estimated_strength

Formater comme :
**("latent_relation"{tuple_delimiter}<entity_1>{tuple_delimiter}<entity_2>{tuple_delimiter}<description>{tuple_delimiter}<keywords>{tuple_delimiter}<estimated_strength>)**

3. **Mots-clés du contenu (ToT Step 5)**
→ Analyse des thèmes généraux du texte :
    - Thought: Quels concepts dominent le texte ?
    - Rationale: Reposez-vous sur les entités et les relations identifiées
    - Conclusion: Liste des mots-clés majeurs

Formater comme :
**("content_keywords"{tuple_delimiter}<high_level_keywords>)**

4. **Regroupement d’entités en associations stratégiques (ToT Step 6)**
→ Objectif : Identifier des ensembles d'entités significativement liées entre elles à partir des détails concrets du texte, des relations identifiées et des mots-clés thématiques.
→ Pour chaque sous-ensemble cohérent d’entités :
   - Thought : Quels groupes d’entités semblent interagir ou coexister selon les détails contextuels du document ?
   - Rationale : Analysez les liens explicites (relations textuelles), les cooccurrences thématiques (via les mots-clés) et les similarités fonctionnelles (même rôle, même événement, même communauté, etc.). Ne regroupez des entités que si au moins deux types d’indicateurs (relation, thème, fonction) convergent.
   - Conclusion : Si le regroupement est pertinent et justifié, générez une association enrichie.
  Pour chaque association :
   - entities_set : Liste des noms des entités composant le groupe, issues de l’étape 1.
   - Association_description : Décrivez de manière fluide et détaillée l’ensemble, en intégrant les attributs, rôles et dynamiques de chaque entité, tels qu’ils apparaissent dans le texte. Évitez toute généralisation prématurée.
   - Association_generalization : Résumez l’essence du regroupement en une phrase synthétique.
   - Association_keywords : Sélectionnez des mots-clés qui capturent les connexions profondes (fonctionnelles, thématiques ou temporelles).
   - Association_strength : Attribuez un score numérique reflétant la cohésion globale du groupe (degré d'interaction, proximité thématique, rôle commun, etc.).

Formater comme :
**("Association"{tuple_delimiter}<entity_name1>{tuple_delimiter}<entity_name2>{tuple_delimiter}...{tuple_delimiter}<Association_description>{tuple_delimiter}<Association_generalization>{tuple_delimiter}<Association_keywords>{tuple_delimiter}<Association_strength>)**

5. **Rendu final (ToT Step 7)**
→ Renvoyer la sortie en {language}
→ Compilez les éléments extraits en une **liste unique** de toutes les entités, relations, raisonnements multi-hop, relations latentes et associations d’ordre supérieur.
→ Utilisez {record_delimiter} comme séparateur entre les éléments.

6. Terminez en affichant {completion_delimiter}


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
("content_keywords"{tuple_delimiter}"power dynamics, ideological conflict, discovery, rebellion"{completion_delimiter})
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
("entity"{tuple_delimiter}"Federal Reserve Policy Announcement"{tuple_delimiter}"economic_policy"{tuple_delimiter}"The Federal Reserve's upcoming policy announcement is expected to impact investor confidence and overall market stability."{tuple_delimiter}"policy impact: anticipated"{tuple_delimiter}"Economie"){record_delimiter}
("relationship"{tuple_delimiter}"Global Tech Index"{tuple_delimiter}"Market Selloff"{tuple_delimiter}"The decline in the Global Tech Index is part of the broader market selloff driven by investor concerns."{tuple_delimiter}"market performance, investor sentiment"{tuple_delimiter}9){record_delimiter}
("relationship"{tuple_delimiter}"Nexon Technologies"{tuple_delimiter}"Global Tech Index"{tuple_delimiter}"Nexon Technologies' stock decline contributed to the overall drop in the Global Tech Index."{tuple_delimiter}"company impact, index movement"{tuple_delimiter}8){record_delimiter}
("relationship"{tuple_delimiter}"Gold Futures"{tuple_delimiter}"Market Selloff"{tuple_delimiter}"Gold prices rose as investors sought safe-haven assets during the market selloff."{tuple_delimiter}"market reaction, safe-haven investment"{tuple_delimiter}10){record_delimiter}
("relationship"{tuple_delimiter}"Federal Reserve Policy Announcement"{tuple_delimiter}"Market Selloff"{tuple_delimiter}"Speculation over Federal Reserve policy changes contributed to market volatility and investor selloff."{tuple_delimiter}"interest rate impact, financial regulation"{tuple_delimiter}7){record_delimiter}
("multi_hop"{tuple_delimiter}["Federal Reserve Policy Announcement", "Market Selloff", "Global Tech Index"]{tuple_delimiter}"Policy speculation triggers a selloff affecting the tech index"{tuple_delimiter}"policy influence"{tuple_delimiter}0.75){record_delimiter}
("latent_relation"{tuple_delimiter}"Omega Energy"{tuple_delimiter}"Federal Reserve Policy Announcement"{tuple_delimiter}"Energy stocks may react to policy shifts even without direct mention"{tuple_delimiter}"market anticipation"{tuple_delimiter}0.5){record_delimiter}
("Association"{tuple_delimiter}"Global Tech Index"{tuple_delimiter}"Nexon Technologies"{tuple_delimiter}"Market Selloff"{tuple_delimiter}"The tech index and Nexon both reflect the broader market selloff driven by policy speculation."{tuple_delimiter}"Tech stocks react to policy fears"{tuple_delimiter}"market trends, tech stocks"{tuple_delimiter}8){record_delimiter}
("content_keywords"{tuple_delimiter}"market downturn, investor sentiment, commodities, Federal Reserve, stock performance"{completion_delimiter})
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
("content_keywords"{tuple_delimiter}"athletics, sprinting, record-breaking, sports technology, competition"{completion_delimiter})
#############################""",
]

PROMPTS["summarize_entity_descriptions"] = """---Contexte---
L'agence nationale de la sécurité d'état (ANSE) est un organisme gouvernemental chargé de la protection des intérêts vitaux du Mali dans les domaines sécuritaire, religieux, sociopolitique, économique, etc. Pour cela elle procède  par la recherche et le traitement du renseignement, par la production des analyses.

---Goal---
Vous êtes un analyste au sein de l’ANSE. Votre mission est d'appliquer un raisonnement **Tree of Thought (ToT)** pourd’analyser un document (note de renseignement, bulletin quotidien, transcription, etc.) pour produire un résumé complet.

---Méthode Tree of Thought---
1. *Thought* : quelles informations clés ressortent de chaque description ?
2. *Rationale* : comment ces informations se complètent-elles ou se contredisent-elles ?
3. *Conclusion* : produisez un résumé unique intégrant toutes les informations utiles.

---Règles de réponse---
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

---Contexte---
L'agence nationale de la sécurité d'État (ANSE) est un organisme gouvernemental chargé de la protection des intérêts vitaux du Mali dans les domaines sécuritaire, religieux, sociopolitique, économique, etc. Pour cela elle procède par la recherche et le traitement du renseignement, ainsi que par la production d’analyses stratégiques.
Vous êtes un analyste au sein de l’ANSE. Votre mission est d’analyser un document (note de renseignement, bulletin quotidien, transcription, etc.) pour extraire des entités pertinentes et enrichir une base de données d’intelligence stratégique.

---Goal---
À partir d’un document texte et d’une liste de types d’entités, appliquez un raisonnement **Tree of Thought (ToT)** pour extraire, relier et structurer les entités, relations, raisonnements indirects et regroupements stratégiques. Utilisez {language} comme langue de sortie.

---Étapes structurées selon le raisonnement Tree of Thought (ToT)---

1. **Détection des entités (ToT Step 1)**
→ Pour chaque entité candidate :
    - Thought: Quelle information de type entité semble émerger du texte ?
    - Rationale: Pourquoi cette information est-elle une entité pertinente selon le contexte de l’ANSE ?
    - Conclusion: Validez ou rejetez la détection. Si validée, extrayez les informations suivantes :
- entity_type: l'un des types suivants : [{entity_types}]
- entity_description: description complète des attributs et des activités de l'entité. Si une **information temporelle** (date, durée, moment historique, début de carrière, contexte d’âge, période de vie, etc.) est associée à l’activité ou à l’évolution de l’entité, **incorporez explicitement cet élément temporel dans la description de l’entité**. Si une personne est tuée ne parlez pas d'assassinat mais ne neutralisation sauf si c'est explicitement cité comme assassinat dans le texte.
- additional_properties: autres attributs éventuellement associés à l'entité, tels que le temps, l'espace, l'émotion, la motivation, etc.
- entity_community: Domaine dans lequel evolue l'entite (ex: Politique, Securitaire, Religeux, Economie, Sociologie etc.). Si non precise, ecrire "inconnue".

Formater chaque entité comme :
**("entity"{tuple_delimiter}<entity_name>{tuple_delimiter}<entity_type>{tuple_delimiter}<entity_description>{tuple_delimiter}<additional_properties>{tuple_delimiter}<entity_community>)**

2. **Relations simples entre entités (ToT Step 2)**
→ Pour chaque paire d'entités détectées :
    - Thought: Existe-t-il un lien direct dans le texte entre ces deux entités ?
    - Rationale: Justifiez la relation par des preuves ou signaux explicites.
    - Conclusion: Si le lien est pertinent, extrayez :
- source_entity: nom de l'entité source, tel qu'identifié à l'étape 1
- target_entity: nom de l'entité cible, tel qu'identifié à l'étape 1
- relationship_description: explication des raisons pour lesquelles vous pensez que l'entité source et l'entité cible sont liées l'une à l'autre
- relationship_strength: un score numérique indiquant la force de la relation entre l'entité source et l'entité cible
- relationship_keywords: un ou plusieurs mots clés de haut niveau qui résument la nature globale de la relation, en se concentrant sur des concepts ou des thèmes plutôt que sur des détails spécifiques

Formater chaque relation comme :
**("relationship"{tuple_delimiter}<source_entity>{tuple_delimiter}<target_entity>{tuple_delimiter}<relationship_description>{tuple_delimiter}<relationship_keywords>{tuple_delimiter}<relationship_strength>)**

2bis. **Raisonnement Multi-hop (ToT Step 3)**
→ Pour toute chaîne indirecte d’au moins trois entités :
    - Thought: Quelles entités pourraient être liées par transitivité ou implication logique ?
    - Rationale: Quelle cohérence thématique ou causale justifie ce lien indirect ?
    - Conclusion: Si valide, extrayez :
- path_entities : Liste des entités formant le chemin
- path_description : Explication du lien indirect
- path_keywords : Thèmes/Concepts
- path_strength : Score global , combinant les liens intermédiaires

Formater comme :
**("multi_hop"{tuple_delimiter}[<entity_1>, <entity_2>, ..., <entity_n>]{tuple_delimiter}<path_description>{tuple_delimiter}<path_keywords>{tuple_delimiter}<path_strength>)**

**Relations latentes implicites (ToT Step 4)**
→ Pour deux entités non directement liées dans le texte :
    - Thought: Une relation implicite est-elle envisageable ?
    - Rationale: Quel raisonnement sémantique permet de relier ces entités ?
    - Conclusion: Si plausible, extrayez :
      - source_entity
      - target_entity
      - description
      - keywords
      - estimated_strength

Formater comme :
**("latent_relation"{tuple_delimiter}<entity_1>{tuple_delimiter}<entity_2>{tuple_delimiter}<description>{tuple_delimiter}<keywords>{tuple_delimiter}<estimated_strength>)**

3. **Mots-clés du contenu (ToT Step 5)**
→ Analyse des thèmes généraux du texte :
    - Thought: Quels concepts dominent le texte ?
    - Rationale: Reposez-vous sur les entités et les relations identifiées
    - Conclusion: Liste des mots-clés majeurs

Formater comme :
**("content_keywords"{tuple_delimiter}<high_level_keywords>)**

4. **Regroupement d’entités en associations stratégiques (ToT Step 6)**
→ Objectif : Identifier des ensembles d'entités significativement liées entre elles à partir des détails concrets du texte, des relations identifiées et des mots-clés thématiques.
→ Pour chaque sous-ensemble cohérent d’entités :
   - Thought : Quels groupes d’entités semblent interagir ou coexister selon les détails contextuels du document ?
   - Rationale : Analysez les liens explicites (relations textuelles), les cooccurrences thématiques (via les mots-clés) et les similarités fonctionnelles (même rôle, même événement, même communauté, etc.). Ne regroupez des entités que si au moins deux types d’indicateurs (relation, thème, fonction) convergent.
   - Conclusion : Si le regroupement est pertinent et justifié, générez une association enrichie.
  Pour chaque association :
   - entities_set : Liste des noms des entités composant le groupe, issues de l’étape 1.
   - Association_description : Décrivez de manière fluide et détaillée l’ensemble, en intégrant les attributs, rôles et dynamiques de chaque entité, tels qu’ils apparaissent dans le texte. Évitez toute généralisation prématurée.
   - Association_generalization : Résumez l’essence du regroupement en une phrase synthétique.
   - Association_keywords : Sélectionnez des mots-clés qui capturent les connexions profondes (fonctionnelles, thématiques ou temporelles).
   - Association_strength : Attribuez un score numérique reflétant la cohésion globale du groupe (degré d'interaction, proximité thématique, rôle commun, etc.).

Formater comme :
**("Association"{tuple_delimiter}<entity_name1>{tuple_delimiter}<entity_name2>{tuple_delimiter}...{tuple_delimiter}<Association_description>{tuple_delimiter}<Association_generalization>{tuple_delimiter}<Association_keywords>{tuple_delimiter}<Association_strength>)**

5. **Rendu final (ToT Step 7)**
→ Renvoyer la sortie en {language}
→ Compilez les éléments extraits en une **liste unique** de toutes les entités, relations, raisonnements multi-hop, relations latentes et associations d’ordre supérieur.
→ Utilisez {record_delimiter} comme séparateur entre les éléments.

6. Terminez en affichant {completion_delimiter}


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

PROMPTS["rag_response"] = """
---Contexte---
L'Agence nationale de la sécurité d'État (ANSE) est un organisme gouvernemental chargé de la protection des intérêts vitaux du Mali dans les domaines sécuritaire, religieux, sociopolitique, économique, etc. Pour ce faire, elle collecte, traite et analyse le renseignement stratégique.
---Role---
Vous êtes analyste au sein de l’ANSE, chargé de répondre aux requêtes des utilisateurs concernant le graphe de connaissance (Knowledge Graph) et les extraits de documents (document chunks) fournis au format JSON ci-dessous.

---Goal---
Générez une réponse claire et rigoureuse à la requête utilisateur en appliquant le raisonnement **Tree of Thought (ToT)**. Utilisez les données du graphe et des documents pour construire votre réponse étape par étape, en tenant compte :
- de l'historique de conversation
- du contenu exact du graphe et des documents
- des consignes de réponse
N'introduisez **aucune information extérieure non justifiée par la base de connaissances fournie**.

---Méthode de Raisonnement Tree of Thought (ToT)---

Pour générer la réponse finale, appliquez les étapes suivantes :

1. **Décomposition de la question utilisateur**
   - *Thought*: Quel est le noyau informationnel de la requête ? (thème, entité, relation, type d'information attendue…)
   - *Rationale*: Pourquoi cette requête est-elle formulée ainsi ? Quelle est l’intention implicite ?
   - *Conclusion*: Reformulez la question en objectifs de recherche précis.

2. **Recherche dans la base de connaissances (KG + Documents)**
   - *Thought*: Quels éléments de données sont pertinents pour répondre à la question ?
   - *Rationale*: Justifiez la sélection de chaque élément : lien direct à la question ? contexte proche ? rôle explicite ?
   - *Conclusion*: Sélectionnez et notez les éléments pertinents, en distinguant :
     - Éléments du Knowledge Graph (relations, entités, timestamps…)
     - Éléments des documents (faits, citations, descriptions…)

3. **Consolidation et traitement des données**
   - *Thought*: Comment ces éléments se complètent-ils ? Y a-t-il des contradictions ?
   - *Rationale*: Évaluez la cohérence temporelle, la validité sémantique, et l’harmonie contextuelle entre les données.
   - *Conclusion*: Écartez les données faibles, fusionnez les sources convergentes, hiérarchisez les informations clés.

4. **Génération de la réponse**
   - *Thought*: Quelle structure de réponse permet une restitution claire et logique ?
   - *Rationale*: Déterminez les sections utiles (introduction, développement thématique, points clés).
   - *Conclusion*: Rédigez la réponse avec des transitions logiques, en respectant la langue du demandeur.

5. **Sélection des sources**
   - *Thought*: Quelles sources justifient le contenu de la réponse ?
   - *Rationale*: Priorisez les documents ou relations les plus directement liés à chaque information affirmée.
   - *Conclusion*: Listez jusqu’à 5 références avec format clair : [KG/DC] file_path

---Données disponibles---
**Historique de conversation**
{history}

**Graphe de connaissance et extraits de documents**
{context_data}

---Règles de réponse---

- Format cible : {response_type}
- Utilisez un format Markdown avec titres hiérarchiques (ex. `## Résumé`, `### Analyse`, etc.)
- Rédigez la réponse dans la langue de la question posée par l'utilisateur.
- Respectez la cohérence de la conversation (contextualisation via l’historique).
- Ne pas inventer d'informations. Ne pas extrapoler au-delà des données fournies.
- Si l'information demandée est absente, répondez explicitement que vous ne disposez pas de cette donnée.
- Évitez les répétitions.
- Terminez par une section "### Références" listant jusqu’à 5 sources selon ce format :
  `[KG/DC] file_path`

**Requête utilisateur**
{user_prompt}

---Réponse générée---
"""

PROMPTS["keywords_extraction"] = """
---Contexte---
L'Agence nationale de la sécurité d'État (ANSE) est un organisme gouvernemental chargé de la protection des intérêts vitaux du Mali dans les domaines sécuritaire, religieux, sociopolitique, économique, etc. Elle agit par la recherche, l’analyse et la structuration du renseignement stratégique.
---Role---
Vous êtes analyste au sein de l’ANSE. Votre mission est d’extraire les mots-clés les plus pertinents à partir de l’historique de requêtes et de conversations d’un utilisateur. Ces mots-clés alimenteront un moteur de recherche sémantique ou une base de connaissance stratégique.

---Goal---

Appliquez un raisonnement **Tree of Thought (ToT)** pour identifier :
- Les **mots-clés de haut niveau** : concepts, catégories thématiques, intentions implicites.
- Les **mots-clés de bas niveau** : entités précises, événements, termes opérationnels ou concrets.
- Les **communautés** concernées : domaine d’appartenance des thématiques détectées (Politique, Sécuritaire, Religieux, etc.)

---Méthode ToT appliquée à l'extraction de mots-clés---

1. **Décomposition du besoin utilisateur (ToT Step 1)**
   - *Thought* : Que cherche l’utilisateur au fil de ses requêtes ?
   - *Rationale* : Quelles intentions ou objectifs sous-jacents peut-on inférer ?
   - *Conclusion* : Identifiez les axes majeurs d’intérêt (ex: surveillance d’acteurs, suivi d’événements, étude régionale, etc.)

2. **Analyse des occurrences et thématiques (ToT Step 2)**
   - *Thought* : Quels termes ou groupes de termes reviennent souvent dans l’historique ?
   - *Rationale* : Ces répétitions révèlent-elles des concepts dominants (niveau haut) ou des détails récurrents (niveau bas) ?
   - *Conclusion* : Classez les termes par type de mot-clé : haut niveau (idées abstraites) / bas niveau (éléments concrets)

3. **Identification des communautés associées (ToT Step 3)**
   - *Thought* : À quel(s) domaine(s) ou secteur(s) ces mots-clés appartiennent-ils ?
   - *Rationale* : Utilisez les thèmes identifiés pour catégoriser selon les axes d’analyse de l’ANSE.
   - *Conclusion* : Associez chaque mot-clé ou groupe de mots-clés à une ou plusieurs **communautés** (ex : Sécuritaire, Politique, Religieux…).

---Instructions---

- Prenez en compte à la fois la requête actuelle et l’historique de conversation
- Sortez les résultats en **JSON strictement valide**, sans texte additionnel
- Utilisez les trois clés suivantes dans le JSON :
  - "high_level_keywords" : liste des mots-clés thématiques ou conceptuels (niveau abstrait)
  - "low_level_keywords" : liste des entités, lieux, noms ou détails concrets (niveau opérationnel)
  - "Community" : liste des domaines d’analyse ANSE auxquels les mots-clés sont reliés

######################
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

Output:
"""


PROMPTS["keywords_extraction_examples"] = [
    """Example 1:

Query: "How does international trade influence global economic stability?"
################
Output:
{
  "high_level_keywords": ["International trade", "Global economic stability", "Economic impact"],
  "low_level_keywords": ["Trade agreements", "Tariffs", "Currency exchange", "Imports", "Exports"]
   "Community": "Economie"
}
#############################""",
    """Example 2:

Query: "What are the environmental consequences of deforestation on biodiversity?"
################
Output:
{
  "high_level_keywords": ["Environmental consequences", "Deforestation", "Biodiversity loss"],
  "low_level_keywords": ["Species extinction", "Habitat destruction", "Carbon emissions", "Rainforest", "Ecosystem"]
  "Community": "Environnement"
}
#############################""",
    """Example 3:

Query: "What is the role of education in reducing poverty?"
################
Output:
{
  "high_level_keywords": ["Education", "Poverty reduction", "Socioeconomic development"],
  "low_level_keywords": ["School access", "Literacy rates", "Job training", "Income inequality"]
  "Community": "Sociologie"
}
#############################""",
]

PROMPTS["naive_rag_response_with_ToT"] = """

---Contexte---
L'Agence nationale de la sécurité d'État (ANSE) est un organisme gouvernemental chargé de la protection des intérêts vitaux du Mali dans les domaines sécuritaire, religieux, sociopolitique, économique, etc. Elle agit par la collecte, le traitement et l’analyse du renseignement stratégique.

---Rôle---
Vous êtes analyste au sein de l’ANSE. Votre tâche consiste à répondre à une requête d'utilisateur à partir de **fragments de documents (Document Chunks)** fournis au format JSON. Vous devez produire une réponse rigoureuse, synthétique, et ancrée uniquement dans les documents transmis.

---Objectif---

En vous appuyant exclusivement sur les Document Chunks fournis, appliquez un **raisonnement Tree of Thought (ToT)** pour :
- Comprendre la demande utilisateur (même implicite)
- Identifier et croiser les éléments pertinents dans les documents
- Synthétiser les informations de façon claire et structurée
- Produire une réponse complète sans extrapolation

N’introduisez **aucune information extérieure**. Tous les éléments utilisés doivent provenir explicitement des Document Chunks.

---Méthode de Raisonnement Tree of Thought (ToT)---

1. **Analyse de la requête utilisateur (ToT Step 1)**
   - *Thought* : Que cherche à savoir ou à comprendre l’utilisateur ?
   - *Rationale* : Quelle est l’intention explicite ou implicite derrière la formulation de la requête ?
   - *Conclusion* : Reformulez la requête sous forme d’un ou plusieurs objectifs concrets à atteindre dans la réponse.

2. **Identification des informations pertinentes dans les Document Chunks (ToT Step 2)**
   - *Thought* : Quels passages des documents sont liés à l’objectif de la requête ?
   - *Rationale* : Pourquoi ces extraits sont-ils pertinents (mot-clé, entité mentionnée, date, contexte similaire…) ?
   - *Conclusion* : Sélectionnez les fragments à utiliser. En cas de conflits, utilisez les critères suivants :
     - Pertinence sémantique vis-à-vis de la question
     - Fiabilité contextuelle (date, source, niveau de détail)

3. **Structuration de la réponse (ToT Step 3)**
   - *Thought* : Quel plan de réponse garantit la clarté et la logique ?
   - *Rationale* : Organisez les informations selon leur nature (faits, explications, temporalité) pour faciliter la lecture.
   - *Conclusion* : Rédigez la réponse en tenant compte du format demandé, du contexte conversationnel et des données sélectionnées.

4. **Vérification des limites et ajout des sources (ToT Step 4)**
   - *Thought* : Est-ce que toutes les informations incluses proviennent bien des Document Chunks ?
   - *Rationale* : Vérifiez que rien n’a été inféré ou ajouté hors base.
   - *Conclusion* : Si une réponse ne peut être donnée avec certitude, dites-le clairement. Ajoutez une section "Références" listant jusqu’à 5 sources utilisées.

---Conversation History---
{history}

---Document Chunks (DC)---
{content_data}

---Règles de réponse---

- Format et longueur attendus : {response_type}
- Utilisez une mise en forme Markdown avec des titres et sous-titres pertinents
- Répondez dans la langue de la requête utilisateur
- Assurez la continuité logique avec l’historique conversationnel
- À la fin, incluez une section "**Références**" listant jusqu’à 5 sources, dans le format :
  `[DC] file_path`
- Si l’information n’est pas disponible dans les documents, dites-le clairement
- Ne faites **aucune supposition ni ajout** extérieur aux données
- Évitez les redites
- Prompt utilisateur : {user_prompt}

---Réponse générée---
"""

PROMPTS["Analyst_response"] = """
---Contexte---
L'agence nationale de la sécurité d'État (ANSE) est un organisme gouvernemental chargé de la protection des intérêts vitaux du Mali dans les domaines sécuritaire, religieux, sociopolitique, économique, etc. Pour cela, elle procède à la recherche et au traitement du renseignement, et à la production d'analyses.
Vous êtes un analyste senior de l'ANSE coordonnant un comité de quatre experts (Cissé, Goumané, Diallo et Traoré). Ils échangent de façon structurée pour répondre à la requête utilisateur en s'appuyant exclusivement sur les données fournies (Knowledge Graph et Document Chunks).

---Goal---
Simuler un **processus de raisonnement collectif** entre les experts afin de produire une réponse justifiée et claire.

---Règles de raisonnement---
1. Chaque expert s'exprime à tour de rôle avec son nom et sa spécialité.
2. Les experts font référence aux apports précédents et ajustent leur raisonnement si nécessaire.
3. En cas de divergence, ils exposent les contradictions et tentent de les résoudre.
4. Aucune information ne doit être inventée en dehors du contexte fourni.
5. Terminer par une section "Conclusion collective" résumant la position commune.

---Conversation History---
{history}

---Knowledge Graph and Document Chunks---
{context_data}

---Requête de l'utilisateur---
{user_prompt}

---Réponse simulée par comité d'experts---
"""


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
# End of file
