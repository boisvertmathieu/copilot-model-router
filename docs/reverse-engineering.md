# Comment Copilot découvre ses modèles

Enquête effectuée le 30 octobre 2026 localement (31 octobre en UTC). Aucune licence Copilot sur cette machine. **Aucune réponse de l'API Copilot réelle n'a été obtenue ou inspectée, et aucune inférence n'a été exécutée.** Les réponses du serveur local décrites plus bas sont entièrement simulées.

« VÉRIFIÉ » signifie qu'un comportement a été lu dans une source identifiable ou observé localement; ça ne veut pas dire qu'il a été validé avec un abonnement. « SUPPOSÉ » désigne une déduction à confirmer sur le poste de travail.

## Sources et reproductibilité

| Élément | Version inspectée | Preuve |
| --- | --- | --- |
| SDK ouvert `github/copilot-sdk` | commit `e22b95e6ead5e1de7e9a68d3087b8d28dc5f364a` | [Code Node](https://github.com/github/copilot-sdk/blob/e22b95e6ead5e1de7e9a68d3087b8d28dc5f364a/nodejs/src/client.ts), [code Python](https://github.com/github/copilot-sdk/blob/e22b95e6ead5e1de7e9a68d3087b8d28dc5f364a/python/copilot/client.py) |
| Paquet `@github/copilot` | `1.0.105`, build `845c22879d4` | [Archive npm](https://registry.npmjs.org/@github/copilot/-/copilot-1.0.105.tgz), chemins `package/package.json`, `package/npm-loader.js` |
| Paquet natif Linux | `@github/copilot-linux-x64@1.0.105` | [Archive npm](https://registry.npmjs.org/@github/copilot-linux-x64/-/copilot-linux-x64-1.0.105.tgz) |
| VS Code Copilot Chat | commit `5863f5a7088958050792b5dccbe8b46c6e13eccc` | [Dépôt officiel](https://github.com/microsoft/vscode-copilot-chat/tree/5863f5a7088958050792b5dccbe8b46c6e13eccc) |
| Couche CAPI de VS Code | `@vscode/copilot-api@0.2.19`, dépendance du commit inspecté | [Archive npm](https://registry.npmjs.org/@vscode/copilot-api/-/copilot-api-0.2.19.tgz), `package/dist/index.js` |

Les empreintes des archives sont dans [research.json](evidence/research.json). Les quatre tables de prix et de clients ont été téléchargées directement de `github/docs`; elles étaient identiques aux copies initiales. Leur URL, leur empreinte et la dernière vérification réseau sont conservées dans `models.yaml`, sous `sync`.

Commandes de recherche utilisées, avec un cache dans un dossier accessible en écriture :

```bash
git clone --depth 1 https://github.com/github/copilot-sdk.git /tmp/cmr-copilot-sdk
npm --cache /tmp/cmr-npm-cache view @github/copilot version dist.tarball --json
npm --cache /tmp/cmr-npm-cache pack @github/copilot@1.0.105 --pack-destination /tmp
npm --cache /tmp/cmr-npm-cache pack @github/copilot-linux-x64@1.0.105 --pack-destination /tmp
```

**VÉRIFIÉ — limite du paquet npm :** le paquet principal est un petit lanceur; il choisit le paquet natif de la plateforme. Le binaire extrait ses fichiers sous `XDG_CACHE_HOME/copilot/pkg/linux-x64/1.0.105/`. On y trouve `cli-main.js`, `schemas/api.schema.json` et `prebuilds/linux-x64/runtime.node`. Le moteur contenant la logique RPC/CAPI est compilé. Lire ses chaînes de texte ne permet pas de reconstituer tout son contrôle de flux. Ce n'est pas le code source ouvert du SDK.

## A. La méthode RPC du SDK

**VÉRIFIÉ — Node :** `CopilotClient.listModels()` envoie `models.list` avec `{}` et retourne `response.models`. Les résultats réussis sont mis en cache jusqu'à la déconnexion; un gestionnaire BYOK `onListModels` peut remplacer complètement cet appel. Voir [`client.ts`, autour de la ligne 2692](https://github.com/github/copilot-sdk/blob/e22b95e6ead5e1de7e9a68d3087b8d28dc5f364a/nodejs/src/client.ts#L2692). Un tel gestionnaire personnalisé ne prouve donc pas l'accès aux modèles Copilot.

**VÉRIFIÉ — protocole :** le SDK lance `copilot --headless --no-auto-update`, ajoute `--stdio` pour son transport par défaut, puis effectue une poignée de main `connect`; les serveurs plus anciens peuvent répondre à `ping`. Les messages JSON-RPC sont cadrés par `Content-Length`, comme LSP. L'enveloppe de requête utile est :

```json
{"jsonrpc":"2.0","id":2,"method":"models.list","params":{}}
```

Voir [`client.ts`, lancement du serveur](https://github.com/github/copilot-sdk/blob/e22b95e6ead5e1de7e9a68d3087b8d28dc5f364a/nodejs/src/client.ts#L3186) et le [transport Python `_jsonrpc.py`](https://github.com/github/copilot-sdk/blob/e22b95e6ead5e1de7e9a68d3087b8d28dc5f364a/python/copilot/_jsonrpc.py#L391).

### Node, avec le SDK

Exemple à exécuter sur le poste de travail après `npm install @github/copilot-sdk@1.0.28` — version npm repérée pendant l'enquête. Le code ouvert a été inspecté au commit ci-dessus; la publication npm n'a pas été soumise à un essai authentifié.

```js
import { CopilotClient } from "@github/copilot-sdk";

const client = new CopilotClient();
try {
  await client.start();
  const auth = await client.getAuthStatus();
  if (!auth.isAuthenticated) throw new Error("Lancer copilot login sur le poste de travail.");
  const models = await client.listModels();
  console.log(JSON.stringify({ source: "models.list", models }, null, 2));
} finally {
  await client.stop();
}
```

La surface RPC générée expose aussi `await client.rpc.models.list({})`, avec des champs additionnels. Son type de requête courant permet un `selectionId` opaque pour choisir un compte ou un `gitHubToken` de compatibilité. Voir [`rpc.ts`, `ModelsListRequest`](https://github.com/github/copilot-sdk/blob/e22b95e6ead5e1de7e9a68d3087b8d28dc5f364a/nodejs/src/generated/rpc.ts#L22754) et [`models.list`](https://github.com/github/copilot-sdk/blob/e22b95e6ead5e1de7e9a68d3087b8d28dc5f364a/nodejs/src/generated/rpc.ts#L38091).

### Python, avec le SDK

Après `python3 -m pip install github-copilot-sdk` dans un environnement virtuel :

```python
import asyncio
import json
from copilot import CopilotClient

async def main():
    client = CopilotClient()
    try:
        await client.start()
        models = await client.list_models()
        print(json.dumps({"source": "models.list", "models": [m.to_dict() for m in models]},
                         ensure_ascii=False, indent=2))
    finally:
        await client.stop()

asyncio.run(main())
```

**VÉRIFIÉ :** `list_models()` fait la même requête RPC. La conversion typée Python `ModelInfo` n'inclut pas nécessairement tous les champs de la surface RPC générée, comme `vendor`; ne pas reconstruire le fournisseur à partir d'un champ perdu. Voir [`client.py`, `list_models`](https://github.com/github/copilot-sdk/blob/e22b95e6ead5e1de7e9a68d3087b8d28dc5f364a/python/copilot/client.py#L4245).

### Le script livré et le serveur externe

[`scripts/list_copilot_models.py`](../scripts/list_copilot_models.py) reproduit ce transport avec la bibliothèque standard Python. Il vérifie `auth.getStatus` avant `models.list`, ne crée aucune session et refuse les demandes d'outils inattendues. Il gère les protocoles 2 et 3, les notifications et les délais. Une erreur d'accès donne le code **4** et ne remplace pas un fichier déjà sauvegardé.

```bash
python3 scripts/list_copilot_models.py --output copilot-models.local.json
```

Pour un serveur externe, la [documentation du SDK](https://github.com/github/copilot-sdk/blob/e22b95e6ead5e1de7e9a68d3087b8d28dc5f364a/docs/getting-started.md#connecting-to-an-external-cli-server) montre `copilot --headless --port 4321`. Le SDK courant peut s'y connecter avec `RuntimeConnection.forUri("127.0.0.1:4321")`. Le script livré utilise plutôt un processus enfant sur stdio, sans port exposé.

**VÉRIFIÉ / distinction :** `--acp` existe dans l'aide du CLI 1.0.105, mais ACP et le protocole RPC du SDK sont deux interfaces. **SUPPOSÉ, donc non utilisé :** que `models.list` serait une méthode ACP. Aucune preuve de cette équivalence n'a été trouvée.

## B. Le HTTP sous-jacent et les jetons

### Observation directe du CLI sur un serveur local

**VÉRIFIÉ EN SIMULATION — CLI 1.0.105, mode SDK :** la [sonde reproductible](evidence/probe_local_http.py) lance le CLI avec `--auth-token-env CMR_RESEARCH_TOKEN --no-auto-login`, un jeton inventé et les URL de service redirigées vers un serveur HTTP local. L'environnement ne reprend aucun jeton de l'utilisateur. Le serveur retourne des données factices; ces données ne vont jamais dans le registre comme disponibilité réelle.

```bash
python3 docs/evidence/probe_local_http.py \
  --cli /chemin/vers/copilot \
  --output /tmp/observation-copilot.json
```

Le [constat enregistré](evidence/local-http.json) montre d'abord `GET /copilot_internal/user`, puis `GET /models`. **Dans ce scénario précis**, le CLI transmet le jeton GitHub fourni directement comme Bearer; aucun échange `/copilot_internal/v2/token` n'a été observé.

En-têtes observés sur `/models` — ce sont des en-têtes **émis par ce CLI**, pas une preuve qu'ils sont tous requis par le serveur réel :

| En-tête | Valeur observée |
| --- | --- |
| `Authorization` | `Bearer <jeton-factice>` |
| `Copilot-Integration-Id` | `copilot-sdk` |
| `Copilot-Harness-Id` | `copilot-sdk` |
| `X-GitHub-Api-Version` | `2026-08-01` |
| `Editor-Version` | `copilot/1.0.105` |
| `OpenAI-Intent` | `conversation-agent` |
| `X-Initiator` | `user` |
| `Accept` et `Content-Type` | `application/json` |
| Autres | `User-Agent`, `X-Client-Machine-Id`, `X-Interaction-Id`, compression |

**VÉRIFIÉ :** le binaire contient la base `https://api.githubcopilot.com` et reconnaît `COPILOT_API_URL`; la sonde confirme la route relative `/models`. **SUPPOSÉ pour un appel réel de ce compte :** l'URL résultante serait `https://api.githubcopilot.com/models`. Aucun accès authentifié ne permet de confirmer l'hôte finalement choisi. Les variantes `https://api.individual.githubcopilot.com/models`, `https://api.business.githubcopilot.com/models` et `https://api.enterprise.githubcopilot.com/models` restent des possibilités de routage à vérifier, pas des valeurs à imposer selon le nom d'un plan.

Un essai local de `models.list` sans licence a donné une liste vide. `auth.getStatus` peut reconnaître des identifiants GitHub sans garantir un droit Copilot. Le script traite donc aussi un catalogue vide comme un échec d'accès. **Aucun résultat du service distant n'est présenté comme vérifié.**

### Le flux VS Code, confirmé dans du code officiel lisible

**VÉRIFIÉ POUR VS CODE :** `fetchCopilotTokenFromGitHubToken()` appelle le type de requête `CopilotToken` avec `Authorization: token <jeton-GitHub>` et `X-GitHub-Api-Version: 2025-04-01`. Voir [`copilotTokenManager.ts`](https://github.com/microsoft/vscode-copilot-chat/blob/5863f5a7088958050792b5dccbe8b46c6e13eccc/src/platform/authentication/node/copilotTokenManager.ts#L259). Dans `@vscode/copilot-api@0.2.19`, `DomainService.tokenURL` construit `https://api.github.com/copilot_internal/v2/token`. La réponse contient notamment `token`, `expires_at`, `refresh_in` et, au besoin, `endpoints.api`. Voir [`TokenEnvelope`](https://github.com/microsoft/vscode-copilot-chat/blob/5863f5a7088958050792b5dccbe8b46c6e13eccc/src/platform/authentication/common/copilotToken.ts#L295).

**VÉRIFIÉ POUR VS CODE :** le même paquet construit `capiModelsURL` à partir de `endpoints.api`, ou de la base de repli `https://api.githubcopilot.com`, puis ajoute `/models`. `ModelMetadataFetcher` utilise le jeton Copilot obtenu et lit `response.data`. Voir [`modelMetadataFetcher.ts`](https://github.com/microsoft/vscode-copilot-chat/blob/5863f5a7088958050792b5dccbe8b46c6e13eccc/src/platform/endpoint/node/modelMetadataFetcher.ts#L233).

La couche réseau de ce commit ajoute Bearer, l'intention `model-access` et la version API `2025-05-01`; la couche CAPI gère l'identifiant d'intégration VS Code. Voir [`networking.ts`](https://github.com/microsoft/vscode-copilot-chat/blob/5863f5a7088958050792b5dccbe8b46c6e13eccc/src/platform/networking/common/networking.ts#L382) et `package/dist/index.js`, méthode `_mixinHeaders`, du paquet CAPI inspecté. **SUPPOSÉ et non recommandé :** recopier ces valeurs VS Code dans une intégration CLI et en attendre le même catalogue.

### Comment obtenir les identifiants GitHub sur le poste de travail

**VÉRIFIÉ DANS LA DOCUMENTATION CLI :** `copilot login` gère OAuth et le stockage des identifiants. Le CLI accepte aussi, par ordre de priorité, `COPILOT_GITHUB_TOKEN`, `GH_TOKEN`, `GITHUB_TOKEN`; les types documentés comprennent le jeton OAuth et le PAT fin avec la permission Copilot Requests. Les PAT classiques `ghp_` ne sont pas pris en charge. Voir la [référence d'authentification du CLI](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-command-reference#copilot-login-options).

Le sélecteur n'obtient ni ne conserve de jeton. Utiliser le SDK ou le script RPC laisse le CLI gérer l'identité, la licence et les changements de routage. L'existence d'un jeton ne prouve pas que l'organisation autorise un modèle.

## C. Les champs du catalogue

| Champ | Vérification et sens |
| --- | --- |
| `id`, `name` | VÉRIFIÉS dans les types SDK et CAPI; identifiant d'appel et nom affiché. |
| `vendor` | VÉRIFIÉ dans le type RPC généré courant; peut nommer l'hébergeur, comme Azure OpenAI, plutôt que l'auteur. Le registre utilise le `provider` officiel des prix pour `family`. |
| `model_picker_enabled`, `preview` | VÉRIFIÉS dans le type HTTP CAPI de VS Code; pas garantis dans toutes les projections SDK. Un modèle présent peut être caché du choix manuel. |
| `policy.state` | VÉRIFIÉ dans le SDK : `enabled`, `disabled`, `unconfigured`. Les deux derniers sont exclus. |
| `billing.multiplier`, `billing.is_premium` | Champs du schéma historique; `is_premium` est présent dans le type HTTP VS Code. Un multiplicateur ne constitue pas un tarif par jeton. |
| `billing.tokenPrices` | Schéma RPC courant : prix d'entrée, de sortie, de cache, `batchSize` et tarif long contexte. Les unités doivent être vérifiées avant toute conversion. |
| `capabilities.limits` | Champs documentés : `max_prompt_tokens`, `max_output_tokens`, `max_context_window_tokens`, limites d'images éventuelles. Aucune valeur distante mesurée ici. |
| Raisonnement | SDK : `supportedReasoningEfforts`, `defaultReasoningEffort`, indicateur `supports.reasoningEffort`; HTTP VS Code : notamment `supports.reasoning_effort`. Ne pas confondre ces formes. |

Sources : [types SDK](https://github.com/github/copilot-sdk/blob/e22b95e6ead5e1de7e9a68d3087b8d28dc5f364a/nodejs/src/types.ts#L4017), [type RPC `Model` et facturation](https://github.com/github/copilot-sdk/blob/e22b95e6ead5e1de7e9a68d3087b8d28dc5f364a/nodejs/src/generated/rpc.ts#L21768), [type HTTP `IModelAPIResponse`](https://github.com/microsoft/vscode-copilot-chat/blob/5863f5a7088958050792b5dccbe8b46c6e13eccc/src/platform/endpoint/common/endpointProvider.ts#L80).

La documentation présente les tarifs RPC en crédits par lot; le schéma plus récent expose aussi `models.listTokenPriceUnits` pour distinguer les unités selon le fournisseur de compte. **Le synchroniseur n'importe pas ces prix dans les tarifs officiels USD** : il conserve les métadonnées sous `runtime` et calcule avec les tables GitHub. Voir la [documentation de facturation SDK](https://docs.github.com/en/copilot/how-tos/copilot-sdk/features/usage-and-billing#per-model-ai-credit-pricing).

## D. Identifiants et différences de version à retenir

**VÉRIFIÉ LOCALEMENT :** `models.getBuiltInCatalog` retourne 68 ID sans authentification. Le [catalogue sauvegardé](evidence/builtin-models.json) confirme l'existence de 25 des 26 ID du registre dans le CLI 1.0.105. `gpt-6.1-terra` reste **SUPPOSÉ**. Le [contrat de cette méthode](https://github.com/github/copilot-sdk/blob/e22b95e6ead5e1de7e9a68d3087b8d28dc5f364a/nodejs/src/generated/rpc.ts#L9757) précise que ce catalogue ne garantit pas les droits ni la disponibilité. Le synchroniseur et le sélecteur refusent donc de l'utiliser comme fichier `--available`.

`GPT-6.1 Sol` existe dans le catalogue intégré, mais n'a pas d'entrée `cli: true` dans la table des clients fournie et téléchargée. Il est exclu du registre actif. `GPT-5.4 nano` et `Claude Sonnet 4` sont exclus pour la même règle de croisement.

**VÉRIFIÉ DANS L'AIDE 1.0.105 :** `--model`, `--context default`, `--max-ai-credits`, `--acp`, ainsi que `--model auto` avec `--auto-tier`. Le brief mentionne `fusion` et `--fusion-tier`; leur validité sur cette version n'a pas été confirmée. On ne s'en sert pas pour imposer un fournisseur indépendant : un routeur peut choisir le même fournisseur que le dev.

La forme Herdr qui transmet les arguments natifs est documentée dans son [historique officiel](https://github.com/herdrdev/herdr/blob/master/CHANGELOG.md#075---2026-07-21). Aucun agent Herdr n'a été lancé ici. L'intégration réelle dans les panneaux WSL et les droits de l'utilisateur demeurent à valider sur le poste de travail.
