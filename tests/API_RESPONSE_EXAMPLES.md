# Exemples de réponses API - Google Family Link

Ce document contient des exemples de réponses réelles des endpoints Google Family Link utilisés dans les tests.

## Endpoint : `timeLimit`

### URL
```
GET /kidsmanagement/v1/people/{account_id}/timeLimit
```

### Paramètres
```
capabilities=TIME_LIMIT_CLIENT_CAPABILITY_SCHOOLTIME
timeLimitKey.type=SUPERVISED_DEVICES
```

### Scénario 1 : Tout activé

**Bedtime activé + School time activé**

```json
[
  ["CAEQBiABKgQIEhABMgQIABAAOAE", 1, [20, 0], [7, 0], null],
  ["CAEQBiACKgQIEhABMgQIABAAOAE", 2, [20, 0], [7, 0], null],
  ["CAEQBiADKgQIEhABMgQIABAAOAE", 3, [20, 0], [7, 0], null],
  ["CAEQBiAEKgQIEhABMgQIABAAOAE", 4, [20, 0], [7, 0], null],
  ["CAEQBiAFKgQIEhABMgQIABAAOAE", 5, [20, 0], [7, 0], null],
  ["CAEQBiAGKgQIEhABMgQIABAAOAE", 6, [20, 0], [7, 0], null],
  ["CAEQBiAHKgQIEhABMgQIABAAOAE", 7, [20, 0], [7, 0], null],
  ["CAMQBiACKgQIEhABMgQIABAAOAE", 1, [17, 0], [20, 0], null],
  ["CAMQBiACKgQIEhABMgQIABAAOAE", 2, [17, 0], [20, 0], null],
  ["CAMQBiACKgQIEhABMgQIABAAOAE", 3, [17, 0], [20, 0], null],
  ["CAMQBiACKgQIEhABMgQIABAAOAE", 4, [17, 0], [20, 0], null],
  ["CAMQBiACKgQIEhABMgQIABAAOAE", 5, [17, 0], [20, 0], null],
  ["487088e7-38b4-4f18-a5fb-4aab64ba9d2f", 1, 2, "1699999999999"],
  ["579e5e01-8dfd-42f3-be6b-d77984842202", 2, 2, "1699999999999"]
]
```

**Parsing :**
- Lignes 1-7 : Schedules bedtime (CAEQ prefix) pour chaque jour de la semaine
- Lignes 8-12 : Schedules school time (CAMQ prefix) pour les jours d'école
- Ligne 13 : **Bedtime revision** - `type_flag=1`, `state_flag=2` → **bedtime_enabled=True**
- Ligne 14 : **School time revision** - `type_flag=2`, `state_flag=2` → **school_time_enabled=True**

### Scénario 2 : Bedtime désactivé

**Bedtime désactivé (stateFlag=1) + School time activé**

```json
[
  ["CAEQBiABKgQIEhABMgQIABAAOAE", 1, [20, 0], [7, 0], null],
  ["CAEQBiACKgQIEhABMgQIABAAOAE", 2, [20, 0], [7, 0], null],
  ["CAMQBiACKgQIEhABMgQIABAAOAE", 1, [17, 0], [20, 0], null],
  ["487088e7-38b4-4f18-a5fb-4aab64ba9d2f", 1, 1, "1699999999999"],
  ["579e5e01-8dfd-42f3-be6b-d77984842202", 2, 2, "1699999999999"]
]
```

**Parsing :**
- Ligne 4 : **Bedtime revision** - `type_flag=1`, `state_flag=1` → **bedtime_enabled=False**
- Ligne 5 : **School time revision** - `type_flag=2`, `state_flag=2` → **school_time_enabled=True**
- **Note** : Les schedules peuvent être présents même si désactivés

### Scénario 3 : School time désactivé

**Bedtime activé + School time désactivé (stateFlag=1)**

```json
[
  ["CAEQBiABKgQIEhABMgQIABAAOAE", 1, [20, 0], [7, 0], null],
  ["CAMQBiACKgQIEhABMgQIABAAOAE", 1, [17, 0], [20, 0], null],
  ["487088e7-38b4-4f18-a5fb-4aab64ba9d2f", 1, 2, "1699999999999"],
  ["579e5e01-8dfd-42f3-be6b-d77984842202", 2, 1, "1699999999999"]
]
```

**Parsing :**
- Ligne 3 : **Bedtime revision** - `type_flag=1`, `state_flag=2` → **bedtime_enabled=True**
- Ligne 4 : **School time revision** - `type_flag=2`, `state_flag=1` → **school_time_enabled=False**

---

## Endpoint : `appliedTimeLimits`

### URL
```
GET /kidsmanagement/v1/people/{account_id}/appliedTimeLimits
```

### Paramètres
```
capabilities=TIME_LIMIT_CLIENT_CAPABILITY_SCHOOLTIME
```

### Scénario 1 : Daily limit activé

**Daily limit activé avec 120 minutes (2 heures)**

```json
[
  null,
  [
    [
      [null, null, 4, "device123"],
      "7200000",
      "3600000",
      null, null, null, null, null, null, null,
      ["CAEQBg", 1, 2, 120, null],
      null, null, null, null, null, null, null, null, null, null, null, null,
      "device123"
    ]
  ]
]
```

**Structure :**
- `[0]` : null
- `[1]` : Liste des devices
  - `[0][0]` : Lock state `[null, null, action_code, device_id]`
    - `action_code=4` → Device unlocked
  - `[0][1]` : Total allowed time = `"7200000"` ms = 120 minutes = 2 heures
  - `[0][2]` : Used time = `"3600000"` ms = 60 minutes = 1 heure
  - `[0][10]` : **Daily limit tuple** = `["CAEQBg", day, state_flag, minutes, null]`
    - `state_flag=2` → **daily_limit_enabled=True**
    - `minutes=120` → **daily_limit_minutes=120**
  - `[0][25]` : Device ID

**Calculs :**
- Total allowed: 7200000 ms ÷ 60000 = 120 minutes
- Used: 3600000 ms ÷ 60000 = 60 minutes
- Remaining: 120 - 60 = 60 minutes

### Scénario 2 : Daily limit désactivé

**Daily limit désactivé (stateFlag=1)**

```json
[
  null,
  [
    [
      [null, null, 4, "device123"],
      "7200000",
      "3600000",
      null, null, null, null, null, null, null,
      ["CAEQBg", 1, 1, 120, null],
      null, null, null, null, null, null, null, null, null, null, null, null,
      "device123"
    ]
  ]
]
```

**Parsing :**
- `[0][10]` : Daily limit tuple avec `state_flag=1` → **daily_limit_enabled=False**
- **Note** : La valeur `minutes=120` est conservée (configuration sauvegardée)

### Scénario 3 : Device locked

**Device verrouillé (action_code=1)**

```json
[
  null,
  [
    [
      [null, null, 1, "device123"],
      "7200000",
      "3600000",
      null, null, null, null, null, null, null,
      ["CAEQBg", 1, 2, 120, null],
      null, null, null, null, null, null, null, null, null, null, null, null,
      "device123"
    ]
  ]
]
```

**Parsing :**
- `[0][0][2]` : `action_code=1` → **Device locked (is_locked=True)**

### Scénario 4 : Time bonus active

**Bonus de temps actif (30 minutes = 1800 secondes)**

```json
[
  null,
  [
    [
      ["override-uuid-123", 1737123456789, 10, "device123", null, null, null, null, null, null, null, null, null, [["1800", 0]]],
      "7200000",
      "3600000",
      null, null, null, null, null, null, null,
      ["CAEQBg", 1, 2, 120, null],
      null, null, null, null, null, null, null, null,
      "0",
      "1800000",
      null, null, null, null,
      "device123"
    ]
  ]
]
```

**Structure du bonus override (position [0]) :**
- `[0][0]` : UUID de l'override (utilisé pour annuler)
- `[0][1]` : Timestamp
- `[0][2]` : Type = 10 (time bonus)
- `[0][3]` : Device ID
- `[0][13][0][0]` : **Bonus en secondes** = `"1800"` (30 minutes)

**Position 19-20 :**
- `[0][19]` : `"0"` (peut contenir des données relatives au bonus, à investiguer)
- `[0][20]` : `"1800000"` ms = 30 minutes de temps utilisé

**Parsing :**
- Bonus minutes = `int(device_data[0][13][0][0]) // 60` = 30 minutes
- Used minutes = `int(device_data[20]) // 60000` = 30 minutes
- **IMPORTANT** : Le bonus **remplace** le temps normal, ne s'ajoute pas
  - Temps restant = 30 minutes (bonus)
  - PAS: 120 (daily limit) - 30 (used) + 30 (bonus) = 120 minutes ❌

### Scénario 5 : Daily limit inactif (jour différent)

**Daily limit configuré mais pour un jour différent (devrait être ignoré)**

```json
[
  null,
  [
    [
      [null, null, 4, "device123"],
      "7200000",
      "0",
      null, null, null, null, null, null, null,
      ["CAEQBg", 2, 2, 120, null],
      null, null, null, null, null, null, null, null, null, null, null, null,
      "device123"
    ]
  ]
]
```

**Parsing (si aujourd'hui = lundi = 1) :**
- `[0][10]` : Daily limit tuple pour le mardi (day=2)
- Même si `state_flag=2` (enabled), ce n'est **pas le jour actuel**
- → `daily_limit_enabled=False` pour aujourd'hui
- → Seuls les tuples avec `day == current_day` sont actifs

---

## Mapping des flags

### State Flags (état ON/OFF)

| Flag | Signification | Utilisation |
|------|---------------|-------------|
| `2` | Activé (ON) | Bedtime, School time, Daily limit |
| `1` | Désactivé (OFF) | Bedtime, School time, Daily limit |

### Type Flags (type de limitation)

| Flag | Type | Endpoint |
|------|------|----------|
| `1` | Bedtime/Downtime | `timeLimit` |
| `2` | School time | `timeLimit` |

### Action Codes (verrouillage device)

| Code | Action | État |
|------|--------|------|
| `1` | Lock | Device verrouillé |
| `4` | Unlock | Device déverrouillé |

### Override Types (timeLimitOverrides)

| Type | Action | Utilisation |
|------|--------|-------------|
| `1` | Lock device | Verrouiller un appareil |
| `4` | Unlock device | Déverrouiller un appareil |
| `8` | Set daily limit | Définir la durée de limite quotidienne |
| `10` | Add time bonus | Ajouter un bonus de temps |

### Préfixes de schedule

| Préfixe | Type de schedule |
|---------|------------------|
| `CAEQ*` | Bedtime/Downtime |
| `CAMQ*` | School time |
| `CAEQBg` | Daily limit tuple |

---

## UUIDs des révisions

### Bedtime (Downtime)
```
487088e7-38b4-4f18-a5fb-4aab64ba9d2f
```

### School time (Evening limit)
```
579e5e01-8dfd-42f3-be6b-d77984842202
```

---

## Jours de la semaine

Les jours dans les schedules sont numérotés :

| Numéro | Jour |
|--------|------|
| `1` | Lundi |
| `2` | Mardi |
| `3` | Mercredi |
| `4` | Jeudi |
| `5` | Vendredi |
| `6` | Samedi |
| `7` | Dimanche |

---

## Format des heures

Les heures sont représentées comme `[heure, minute]` :

```json
[20, 0]  // 20h00
[7, 30]  // 7h30
[17, 15] // 17h15
```

---

## Notes importantes

1. **Schedules vs État** : Les schedules peuvent être présents même si la fonctionnalité est désactivée
2. **Conservation des valeurs** : Les minutes configurées (daily_limit_minutes) sont conservées même si désactivé
3. **Multiple devices** : `appliedTimeLimits` retourne un array de devices, chacun avec ses propres limites
4. **Timestamps** : Les timestamps sont en millisecondes epoch (format JavaScript)
5. **Null values** : Beaucoup de valeurs null dans les réponses sont des placeholders pour la structure de l'API
