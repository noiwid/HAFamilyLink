# Templates de Debug pour Home Assistant

## Instructions
Copiez ces templates dans **Configuration → Outils de développement → Template**

## 1. Voir toutes les données d'un enfant

```yaml
{% set child_name = "Macéo Collin" %}
{% set coordinator_data = state_attr('sensor.' + child_name.lower().replace(' ', '_') + '_screen_time', 'data') %}

Nom: {{ child_name }}

=== RAW DATA ===
{{ coordinator_data }}

=== DEVICES ===
{% for device in coordinator_data.devices %}
Device: {{ device.name }}
  - ID: {{ device.id }}
  - Status: {{ device.status }}
  - Daily limit enabled: {{ device.daily_limit_enabled }}
  - Daily limit minutes: {{ device.daily_limit_minutes }}
  - Total allowed: {{ device.total_allowed_minutes }}
  - Used: {{ device.used_minutes }}
  - Remaining: {{ device.remaining_minutes }}
  - Bedtime active: {{ device.bedtime_active }}
  - Schooltime active: {{ device.schooltime_active }}
{% endfor %}
```

## 2. Voir les états des sensors/binary sensors

```yaml
{% set child_name = "maceo_collin" %}

=== SENSORS ===
Screen Time: {{ states('sensor.' + child_name + '_screen_time') }}
Screen Time Remaining: {{ states('sensor.' + child_name + '_screen_time_remaining') }}
Next Restriction: {{ states('sensor.' + child_name + '_next_restriction') }}

=== BINARY SENSORS ===
Daily Limit Reached: {{ states('binary_sensor.' + child_name + '_daily_limit_reached') }}

=== DEVICES ===
{% for device_state in states.sensor %}
  {% if child_name in device_state.entity_id and 'bedtime_active' in device_state.entity_id %}
Bedtime Active ({{ device_state.entity_id }}): {{ device_state.state }}
  {% endif %}
  {% if child_name in device_state.entity_id and 'schooltime_active' in device_state.entity_id %}
Schooltime Active ({{ device_state.entity_id }}): {{ device_state.state }}
  {% endif %}
{% endfor %}
```

## 3. Voir les attributs détaillés

```yaml
{% set entity = 'sensor.maceo_collin_screen_time_remaining' %}

Entity: {{ entity }}
State: {{ states(entity) }}
Attributes:
{{ state_attr(entity, '') }}
```

## 4. Liste tous les boutons/switches disponibles

```yaml
=== SWITCHES ===
{% for entity in states.switch %}
  {% if 'maceo' in entity.entity_id.lower() %}
{{ entity.entity_id }}: {{ entity.state }}
  {% endif %}
{% endfor %}

=== BUTTONS ===
{% for entity in states.button %}
  {% if 'maceo' in entity.entity_id.lower() %}
{{ entity.entity_id }}: {{ entity.state }}
  {% endif %}
{% endfor %}
```
