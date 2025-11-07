# Google Family Link Services

Cette intégration fournit 4 services pour contrôler les applications de l'appareil supervisé.

## 📱 Services disponibles

### 1. `familylink.block_device_for_school`
Bloque toutes les applications sauf les essentielles pour simuler un verrouillage de l'appareil pendant les heures de classe.

**Applications essentielles (toujours autorisées par défaut):**
- Téléphone (`com.android.dialer`)
- Contacts (`com.android.contacts`)
- SMS/Messages (`com.android.mms`, `com.google.android.apps.messaging`)
- Paramètres (`com.android.settings`)
- Horloge/Alarme (`com.android.deskclock`)
- Google Maps (`com.google.android.apps.maps`)
- Urgence (`com.android.emergency`)
- Services système essentiels

**Paramètres:**
- `whitelist` (optionnel): Liste d'applications supplémentaires à autoriser

**Exemple:**
```yaml
service: familylink.block_device_for_school
data:
  whitelist:
    - com.example.educationalapp
    - com.microsoft.teams
```

---

### 2. `familylink.unblock_all_apps`
Débloque toutes les applications pour terminer le mode école et restaurer l'utilisation normale de l'appareil.

**Paramètres:** Aucun

**Exemple:**
```yaml
service: familylink.unblock_all_apps
```

---

### 3. `familylink.block_app`
Bloque une application spécifique par son nom de package.

**Paramètres:**
- `package_name` (requis): Nom du package Android (ex: `com.youtube.android`)

**Exemple:**
```yaml
service: familylink.block_app
data:
  package_name: com.youtube.android
```

---

### 4. `familylink.unblock_app`
Débloque une application spécifique par son nom de package.

**Paramètres:**
- `package_name` (requis): Nom du package Android

**Exemple:**
```yaml
service: familylink.unblock_app
data:
  package_name: com.youtube.android
```

---

## 🤖 Exemples d'automations

### Automation: Bloquer le téléphone pendant les heures de classe

```yaml
automation:
  - alias: "Bloquer téléphone pendant les cours"
    description: "Bloque toutes les apps sauf essentielles de 8h à 15h30 en semaine"
    trigger:
      - platform: time
        at: "08:00:00"
    condition:
      - condition: time
        weekday:
          - mon
          - tue
          - wed
          - thu
          - fri
    action:
      - service: familylink.block_device_for_school
        data:
          whitelist:
            - com.microsoft.teams  # Autoriser Teams pour l'école
      - service: notify.mobile_app_parent_phone
        data:
          title: "Mode École Activé"
          message: "Le téléphone est bloqué jusqu'à 15h30"

  - alias: "Débloquer après l'école"
    description: "Débloque le téléphone après l'école"
    trigger:
      - platform: time
        at: "15:30:00"
    condition:
      - condition: time
        weekday:
          - mon
          - tue
          - wed
          - thu
          - fri
    action:
      - service: familylink.unblock_all_apps
      - service: notify.mobile_app_parent_phone
        data:
          title: "Mode École Terminé"
          message: "Le téléphone est débloqué"
```

### Automation: Bloquer YouTube après 21h

```yaml
automation:
  - alias: "Bloquer YouTube le soir"
    trigger:
      - platform: time
        at: "21:00:00"
    action:
      - service: familylink.block_app
        data:
          package_name: com.youtube.android
      - service: familylink.block_app
        data:
          package_name: com.google.android.youtube

  - alias: "Débloquer YouTube le matin"
    trigger:
      - platform: time
        at: "07:00:00"
    action:
      - service: familylink.unblock_app
        data:
          package_name: com.youtube.android
      - service: familylink.unblock_app
        data:
          package_name: com.google.android.youtube
```

### Automation: Bloquer selon le temps d'écran

```yaml
automation:
  - alias: "Bloquer si trop de temps d'écran"
    trigger:
      - platform: state
        entity_id: sensor.family_link_daily_screen_time
    condition:
      - condition: numeric_state
        entity_id: sensor.family_link_daily_screen_time
        above: 120  # 2 heures en minutes
    action:
      - service: familylink.block_device_for_school
      - service: notify.mobile_app_parent_phone
        data:
          title: "Limite de Temps d'Écran Atteinte"
          message: >
            Temps d'écran: {{ states('sensor.family_link_screen_time_formatted') }}
            L'appareil a été bloqué.
```

### Automation: Emploi du temps personnalisé

```yaml
automation:
  - alias: "Mode école - Lundi"
    trigger:
      - platform: time
        at: "08:00:00"
    condition:
      - condition: time
        weekday: mon
    action:
      - service: familylink.block_device_for_school
        data:
          whitelist:
            - com.microsoft.teams  # Cours en ligne

  - alias: "Mode école - Mercredi (demi-journée)"
    trigger:
      - platform: time
        at: "08:00:00"
    condition:
      - condition: time
        weekday: wed
    action:
      - service: familylink.block_device_for_school

  - alias: "Débloquer mercredi midi"
    trigger:
      - platform: time
        at: "12:00:00"
    condition:
      - condition: time
        weekday: wed
    action:
      - service: familylink.unblock_all_apps
```

---

## 🔍 Comment trouver les noms de packages

1. **Via le capteur `sensor.family_link_installed_apps`:**
   - Consultez les attributs du capteur dans Developer Tools → States
   - Cherchez l'app dans la liste

2. **Via le capteur `sensor.family_link_blocked_apps`:**
   - Les apps bloquées affichent leur nom et package

3. **Via le capteur `sensor.family_link_top_app_X`:**
   - Consultez l'attribut `package_name` de chaque top app

4. **Via Google Play Store:**
   - URL de l'app: `https://play.google.com/store/apps/details?id=com.example.app`
   - Le `id=` est le package name

---

## ⚠️ Notes importantes

1. **Délai entre les blocages:** Les services ajoutent un délai de 0,1s entre chaque app pour éviter le rate limiting de Google

2. **Rafraîchissement automatique:** Après chaque appel de service, les données sont automatiquement rafraîchies

3. **Apps système:** Certaines apps système ne peuvent pas être bloquées pour ne pas casser l'appareil

4. **Persistance:** Les blocages persistent jusqu'à ce que vous les débloquiez manuellement ou via automation

5. **Plusieurs enfants:** Si vous avez plusieurs enfants supervisés, les services affectent le premier enfant trouvé. Pour cibler un enfant spécifique, contactez le développeur pour une future mise à jour.

---

## 📊 Capteurs complémentaires

Utilisez ces capteurs pour créer des automations intelligentes:

- `sensor.family_link_daily_screen_time` - Temps d'écran total en minutes
- `sensor.family_link_screen_time_formatted` - Temps formaté (HH:MM:SS)
- `sensor.family_link_installed_apps` - Nombre d'apps installées
- `sensor.family_link_blocked_apps` - Nombre et liste des apps bloquées
- `sensor.family_link_apps_with_time_limits` - Apps avec limites de temps
- `sensor.family_link_top_app_1` à `#10` - Top 10 apps les plus utilisées
- `sensor.family_link_child_info` - Infos sur l'enfant supervisé

---

## 🆘 Dépannage

### Le service ne bloque pas les apps
- Vérifiez que l'authentification est active (add-on lancé et cookies valides)
- Consultez les logs dans Home Assistant: Configuration → Logs
- Cherchez `familylink` dans les logs

### Les apps se débloquent toutes seules
- Vérifiez qu'il n'y a pas d'automations conflictuelles
- Vérifiez que les parents n'ont pas débloqué depuis l'app Family Link

### L'appareil est complètement bloqué
- Appelez le service `familylink.unblock_all_apps`
- Si ça ne fonctionne pas, déverrouillez depuis l'app Family Link mobile

---

## 🔄 Workflow recommandé

1. **Testez d'abord manuellement** depuis Developer Tools → Services
2. **Vérifiez les logs** pour confirmer le succès
3. **Créez les automations** une fois les tests réussis
4. **Testez les automations** en changeant temporairement les heures
5. **Activez en production** avec les vraies heures de classe

---

## 📝 Exemple complet: Gestion complète du temps d'écran

```yaml
# Horaires scolaires
automation:
  - id: school_mode_on
    alias: "Activer mode école"
    trigger:
      - platform: time
        at: "08:00:00"
    condition:
      - condition: time
        weekday: [mon, tue, wed, thu, fri]
    action:
      - service: familylink.block_device_for_school
      - service: notify.parent
        data:
          message: "📚 Mode école activé"

  - id: school_mode_off
    alias: "Désactiver mode école"
    trigger:
      - platform: time
        at: "15:30:00"
    condition:
      - condition: time
        weekday: [mon, tue, wed, thu, fri]
    action:
      - service: familylink.unblock_all_apps
      - service: notify.parent
        data:
          message: "✅ Mode école désactivé"

# Heure du coucher
  - id: bedtime_block_apps
    alias: "Bloquer apps au coucher"
    trigger:
      - platform: time
        at: "21:00:00"
    action:
      - service: familylink.block_device_for_school
      - service: notify.parent
        data:
          message: "😴 Heure du coucher - Téléphone bloqué"

  - id: morning_unblock
    alias: "Débloquer le matin"
    trigger:
      - platform: time
        at: "07:00:00"
    action:
      - service: familylink.unblock_all_apps
      - service: notify.parent
        data:
          message: "☀️ Bonjour - Téléphone débloqué"

# Limite de temps d'écran
  - id: screen_time_limit
    alias: "Bloquer si limite atteinte"
    trigger:
      - platform: numeric_state
        entity_id: sensor.family_link_daily_screen_time
        above: 180  # 3 heures
    action:
      - service: familylink.block_device_for_school
      - service: notify.parent
        data:
          title: "⏱️ Limite de temps atteinte"
          message: >
            Temps d'écran aujourd'hui: {{ states('sensor.family_link_screen_time_formatted') }}
            Téléphone bloqué jusqu'à demain.
```

---

## 🎯 Prochaines fonctionnalités (en développement)

- Support multi-enfants (choisir quel enfant cibler)
- Gestion des limites de temps par app
- Web scraping pour verrouiller physiquement l'appareil
- Historique du temps d'écran sur 7 jours
- Notifications push vers l'enfant
