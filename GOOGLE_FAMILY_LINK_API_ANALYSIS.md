
# Google Family Link – API Analysis (consolidé)

> **But** : documenter les endpoints observés, les capabilities utiles, **la structure exacte des réponses** (notamment `timeLimit` & `appliedTimeLimits`), et fournir un **guide de parsing robuste** + scénarios de test.  
> **Contexte** : déductions confirmées à partir de captures réelles (logs/dumps) et de l’interface Family Link. Ce document vise l’exploitation _client_ (lecture), pas l’ingénierie inverse complète du protocole propriétaire.

---

## ⚠️ Avertissement
- L’API n’est **pas publique** et peut changer sans préavis.  
- Les formats sont **proto/JSON-like** avec beaucoup d’arrays **positionnels** (index sensibles).  
- Les exemples ci-dessous sont **fiables** dans le périmètre observé, mais restent sujets à évolution côté Google.

---

## 🔐 Authentification & en-têtes nécessaires (observé)

- `Authorization: SAPISIDHASH <hash>`
- `X-Goog-AuthUser: 0`
- `X-Goog-Api-Key: <key>`
- `Content-Type: application/json+protobuf` (ou `application/json protobuf` selon l’outil)
- `x-goog-ext-223261916-bin: ...`
- `x-goog-ext-202964622-bin: ...`
- `x-goog-ext-198889211-bin: ...`

> Ces `x-goog-ext-*` varient par session / navigateur. Conserver tels quels côté client, sans journaliser en clair.

---

## 🧭 Endpoints (lecture)

| Capability / Domaine | Endpoint | Query / Notes |
|---|---|---|
| **Restrictions** (politiques appareil) | `/kidsmanagement/v1/people/{childId}/restrictions:listByGroups` | Renvoie les restrictions par groupes (ex. DISALLOW_ADD_USER, DISALLOW_DEBUGGING_FEATURES, etc.). |
| **Paramètres globaux (menu “settings”)** | `/kidsmanagement/v1/people/settingResources` | Liste des “sections” de réglages (Play, YouTube, Chrome/Web, Search, Communication, Assistant, Gemini, App limits, Location, Devices). |
| **Localisation – écran d’activation** | `/kidsmanagement/v1/people/{childId}/location/settings` *(via settingResources path)* | Texte d’information + explications par device. |
| **Photos membres famille** | `/kidsmanagement/v1/families/mine/familyMembersPhotos` | `pageSize`, `supportedPhotoOrigins=...` (GOOGLE_PROFILE, FAMILY_MEMBERS_PHOTO, etc.). |
| **Notifications** | `/kidsmanagement/v1/people/me/notificationElements?clientCapabilities=CAPABILITY_TIMEZONE&userTimeZone=Europe/Paris` | Événements (ex. _Nouvelle application installée_). |
| **Apps & usage** | `/kidsmanagement/v1/people/{childId}/appsandusage?capabilities=CAPABILITY_APP_USAGE_SESSION&capabilities=CAPABILITY_SUPERVISION_CAPABILITIES` | Liste d’apps (package, nom, icône, devices) + (dans d’autres réponses) planifications **downtime/schooltime** (heures). |
| **TimeLimit (programmation)** | `/kidsmanagement/v1/people/{childId}/timeLimit?capabilities=TIME_LIMIT_CLIENT_CAPABILITY_SCHOOLTIME&timeLimitKey.type=SUPERVISED_DEVICES` | **Programmation** Bedtime & Schooltime + **switches globaux** (ON/OFF) via “révisions”. |
| **AppliedTimeLimits (état appliqué)** | `/kidsmanagement/v1/people/{childId}/appliedTimeLimits?capabilities=TIME_LIMIT_CLIENT_CAPABILITY_SCHOOLTIME` | **État du jour par device** : limites quotidiennes, fenêtres actives, agrégats autorisé/consommé. |

> D’autres endpoints existent sans être exhaustifs ici (liste “capabilities” non publique). Ce doc couvre ceux nécessaires à la lecture **bedtime/schooltime/daily-limit** & usage d’apps/notifications/photos.

---

## 🧱 Modèles de données — clés observées

### 1) `timeLimit` — **Programmation** (théorique)
- Contient **les créneaux** pour chaque jour + **révisions** indiquant l’état **global ON/OFF** de Bedtime & Schooltime.
- Deux familles de tuples (dans un grand tableau) :  
  - **Bedtime** : entrées **`CAEQ*`** (par jour)  
  - **Schooltime** : entrées **`CAMQ*`** (par jour)

#### 1.1. Tuples `CAEQ*` (Bedtime / Downtime)
```
["CAEQAQ"|"CAEQAg"|..., day, stateFlag, [startH,startM], [endH,endM], createdEpochMs, updatedEpochMs, policyId]
```
- `day` : 1..7 (lundi..dimanche)
- `stateFlag` : **2 = ON**, **1 = OFF** (pour ce jour)
- `start/end` : heures locales (24h)
- `policyId` : identifiant interne (ex. `487088e7-...`) — utile pour croiser avec “révisions”

#### 1.2. Tuples `CAMQ*` (Schooltime)
```
["CAMQAS..."|..., day, stateFlag, [startH,startM], [endH,endM], createdEpochMs, updatedEpochMs, policyId]
```
- Même sémantique que `CAEQ*`, pour le domaine **Schooltime**.

#### 1.3. Bloc “révisions” (états globaux ON/OFF)
En fin de réponse, un bloc de tuples indique l’état global des switches :
```
[ policyId, type, state, [sec, nanos] ]
```
- `type` : **1 = Bedtime**, **2 = Schooltime**
- `state` : **2 = ON**, **1 = OFF**
- `policyId` : correspond aux `policyId` vus dans les tuples `CAEQ*/CAMQ*`

> Le tout **premier entier** du 1er gros bloc reflète **souvent** l’état global Bedtime (`2` quand ON, `1` quand OFF). Ne pas s’y fier seul : utiliser les **révisions** comme source de vérité.

---

### 2) `appliedTimeLimits` — **État appliqué aujourd’hui (par device)**
- Chaque **device** apparaît dans un **bloc**. À l’intérieur, on retrouve :
  - **Daily limit (minutes)** sous forme de tuple **`CAEQBg`** avec une **valeur minutes**.
  - **Bedtime** (fenêtre) via tuple **`CAEQBg`** mais **avec heures `[start],[end]`** (oui, même clé racine, contenu différent).
  - **Schooltime** via un tuple **`CAMQ*`** (ex. `CAMQBi...`) avec **heures** et `stateFlag`.
  - Des **agrégats** “autorisé / consommé” sur la journée (souvent deux entiers proches, parfois `0` si OFF).

#### 2.1. Daily limit (par device & par jour)
```
["CAEQBg", day, stateFlag, minutes, createdEpochMs, updatedEpochMs]
```
- `stateFlag` : **2 = ON**, **1 = OFF**
- `minutes` : quota journalier (ex. `120` pour 2h)
- **ON** si `stateFlag == 2` **ET** `minutes > 0`

#### 2.2. Bedtime (fenêtre appliquée ce jour, par device)
```
["CAEQBg", day, stateFlag, [startH,startM], [endH,endM], createdEpochMs, updatedEpochMs, policyId]
```
- `stateFlag` : **2 = ON**, **1 = OFF**
- Horaires dans le tuple. Chevauche minuit si `end < start`.

#### 2.3. Schooltime (fenêtre appliquée ce jour, par device)
```
["CAMQBi...", day, stateFlag, [startH,startM], [endH,endM], createdEpochMs, updatedEpochMs, policyId]
```
- `stateFlag` : **2 = ON**, **1 = OFF**

> **Remarque** : `appliedTimeLimits` peut résumer plusieurs **policies** mais ne garantit pas une “flatten” parfaite. Se fier au **jour courant** et aux tuples présents pour la **détection ON/OFF**.

---

## 🧭 Indexation (positions critiques)

### Tuples horaires (bedtime/schooltime)
```
[ key, day(1), stateFlag(2), start(3), end(4), createdMs(5), updatedMs(6), policyId(7) ]
```
- `stateFlag ∈ {1,2}`
- `start/end` : 2-uplets `[hh,mm]`

### Daily limit (minutes)
```
[ "CAEQBg", day(1), stateFlag(2), minutes(3), createdMs(4), updatedMs(5) ]
```

### Révisions (timeLimit, fin de réponse)
```
[ policyId(0), type(1), state(2), [sec(3).0, nanos(3).1] ]
```

> Dans certains dumps, des champs additionnels précèdent/suivent (null, zéros, timestamps) — **ne jamais indexer en absolu** sur toute la ligne, mais **repérer la clé racine** (`"CAEQ..."`/`"CAMQ..."`) puis parser **relativement**.

---

## ✅ Matrice des scénarios (vérifié)

| Scénario | Bedtime (global) | Schooltime (global) | Daily limit |
|---|---:|---:|---:|
| 1. Bedtime ON, School ON, Daily ON | `timeLimit: revisions → type=1, state=2` | `revisions → type=2, state=2` | `appliedTimeLimits: ["CAEQBg", d, 2, minutes>0]` |
| 2. Bedtime OFF, School ON, Daily ON | `revisions → type=1, state=1` | `revisions → type=2, state=2` | idem (ON) |
| 3. Bedtime OFF, School OFF, Daily ON | `revisions → type=1, state=1` | `revisions → type=2, state=1` | idem (ON) |
| 4. Daily OFF (par device) | (selon précédent) | (selon précédent) | `appliedTimeLimits: ["CAEQBg", d, 1, minutes]` **ou** agrégats du jour à `0` |

> **Note** : la **programmation** (les tuples `CAEQ*/CAMQ*` dans `timeLimit`) reste **présente** même si le **switch global** est OFF. C’est le **state global** (révisions) qui arbitre l’application.

---

## 🧪 Parsing — Algorithme conseillé (pseudo-code)

```python
def parse_time_limit(payload):
	# 1) Extraire programmation Bedtime (CAEQ*) et Schooltime (CAMQ*)
	bedtime = extract_schedules(payload, key_prefix="CAEQ")
	school  = extract_schedules(payload, key_prefix="CAMQ")

	# 2) Lire l’état global ON/OFF via révisions (source de vérité)
	globals = extract_revisions(payload)  # { bedtime: on/off, school: on/off }

	return {
		"bedtime_schedules": bedtime,   # [{day,start,end,policyId,stateFlag}]
		"schooltime_schedules": school, # idem
		"global": globals               # {"bedtime": True/False, "schooltime": True/False}
	}

def parse_applied_time_limits(payload, today_day):
	devices = []
	for dev in iterate_devices(payload):
		daily = find_tuple(dev, key="CAEQBg", day=today_day, form="minutes")
		bed   = find_tuple(dev, key="CAEQBg", day=today_day, form="window")
		school= find_tuple(dev, key_prefix="CAMQ", day=today_day, form="window")

		devices.append({
			"device_id": extract_device_id(dev),
			"daily_limit_on": daily and daily.stateFlag == 2 and daily.minutes > 0,
			"daily_limit_minutes": daily.minutes if daily else 0,
			"bedtime_on": bed and bed.stateFlag == 2,
			"bedtime_window": bed and (bed.start, bed.end),
			"schooltime_on": school and school.stateFlag == 2,
			"schooltime_window": school and (school.start, school.end),
			"allowed_used_ms": extract_aggregates(dev)  # optionnel
		})
	return devices
```

**Règles d’interprétation** :
- `stateFlag == 2` → **ON**, `1` → **OFF** (valable pour toutes les familles de tuples).
- `minutes > 0` requis pour considérer la **daily limit** active.
- Les **heures** sont locales (Europe/Paris si contexte utilisateur ; attention au DST).  
- Les fenêtres `start > end` **chevauchent minuit** (ex. 20:30 → 07:30).

---

## 🧩 Champs agrégés (appliedTimeLimits)
Dans chaque bloc device, deux entiers (souvent contigus) représentent l’**autorisé/consommé** du jour (ms). Ils peuvent être `0` si la limite est **OFF** même si une valeur minute existe dans le tuple.

---

## 🧷 Apps & Usage (`appsandusage`)
- **Liste d’apps** (package, label, icône, devices). Exemple d’item :
```
[ packageName, appName, iconUrl, [], installedEpochMs, null, 0, 1, null, null, deviceCount, [deviceIds...], stateFlag ]
```
- `stateFlag` (en fin) : statut par app côté supervision (observé 1/2).  
- D’autres formes de cette réponse peuvent inclure les fenêtres **downtime/schooltime** (heures) et révisions (horodotées).

---

## 📣 Notifications (`notificationElements`)
- Ex. “Nouvelle application installée” avec **horodatage** (`["1763148569", 431000000]`) et **liens** vers l’app concernée (`/member/{childId}/app/{package}`).  
- `clientCapabilities=CAPABILITY_TIMEZONE` + `userTimeZone=Europe/Paris` conseillés pour des timestamps locaux.

---

## 🖼️ Photos famille (`familyMembersPhotos`)
- Réponse : `[ personId, null, photoUrl, origin, familyId, optionalColor ]`  
- `supportedPhotoOrigins=` : `GOOGLE_PROFILE`, `FAMILY_MEMBERS_PHOTO`, `DEFAULT_SILHOUETTE`, `CHILD_DEFAULT_AVATAR`, `UNKNOWN_PHOTO_ORIGIN`.

---

## ❗ Points d’attention & bonnes pratiques client

- **Ne pas indexer en dur** sur toute la ligne : _matcher la clé racine_ (`"CAEQ..."` / `"CAMQ..."`) puis interpréter **relativement**.
- **Tolérance aux `null`/champs absents** : prévoir des `get()`/`try` sur les positions.
- **Horaires** : toujours **normaliser** `[hh,mm]` (0–23 / 0–59) ; gérer **minuit** (`end < start`).
- **Fusos & DST** : convertir les epoch ms → `datetime` local ; préférer des utilitaires timezone-aware.
- **Secrets** : ne jamais logger les headers auth/keys ; masquer dans diagnostics.
- **Rate limiting** : retries bornés (429/5xx) + backoff + jitter ; 401/403 → reauth/config.

---

## 🧪 Tests (recommandé)
- **Fixtures** 4 scénarios :  
  1. Bedtime ON + School ON + Daily ON  
  2. Bedtime OFF + School ON + Daily ON  
  3. Bedtime OFF + School OFF + Daily ON  
  4. Daily OFF (par device), avec comparaison entre 2 devices
- **Asserts** :  
  - `daily_limit_on`, `daily_limit_minutes` corrects par device/jour.  
  - `bedtime_on`, `schooltime_on` + fenêtres `[start,end]`.  
  - Mapping `revisions` (type=1/2 → state=2/1).

---

## 📝 Glossaire rapide
- **CAEQ*** : famille Bedtime ou Daily (selon charge utile : minutes vs fenêtre).  
- **CAMQ*** : famille Schooltime.  
- **stateFlag** : 2=ON, 1=OFF.  
- **policyId** : identifiant de règle (liaison avec révisions).

---

## ❓ Manques connus / Ouvertures
- **Liste exhaustive des capabilities** : non publique ; documenter **à l’usage**.  
- **Schéma proto complet** : non disponible ; rester défensif côté parsing.  
- **Agrégats “allowed/used ms”** : positions exactes non garanties → détecter par clé/structure lorsque présent.

---

*Dernière mise à jour : générée depuis l’analyse des dumps concrets et de l’UI Family Link. PRs bienvenues si vous observez des variantes.*
