# Templates de Debug pour Home Assistant (CORRIGÉS)

## 1. Voir les attributs de Screen Time Remaining (par device)

```yaml
{%- set child_name = "maceo_collin" %}

=== DEVICES - SCREEN TIME REMAINING ===
{%- for entity in states.sensor %}
  {%- if child_name in entity.entity_id and 'screen_time_remaining' in entity.entity_id %}

{{ entity.name }}:
  State: {{ entity.state }}
  Attributes: {{ entity.attributes }}
  {%- endif %}
{%- endfor %}
```

## 2. Voir les attributs de Next Restriction (par device)

```yaml
{%- set child_name = "maceo_collin" %}

=== DEVICES - NEXT RESTRICTION ===
{%- for entity in states.sensor %}
  {%- if child_name in entity.entity_id and 'next_restriction' in entity.entity_id %}

{{ entity.name }}:
  State: {{ entity.state }}
  Attributes: {{ entity.attributes }}
  {%- endif %}
{%- endfor %}
```

## 3. Voir tous les binary sensors (bedtime/schooltime active)

```yaml
{%- set child_name = "maceo_collin" %}

=== BINARY SENSORS ===
{%- for entity in states.binary_sensor %}
  {%- if child_name in entity.entity_id %}

{{ entity.name }}:
  State: {{ entity.state }}
  Device Class: {{ entity.attributes.device_class }}
  Attributes: {{ entity.attributes }}
  {%- endif %}
{%- endfor %}
```

## 4. Voir tous les switches

```yaml
{%- set child_name = "maceo_collin" %}

=== SWITCHES ===
{%- for entity in states.switch %}
  {%- if child_name in entity.entity_id %}

{{ entity.name }}:
  State: {{ entity.state }}
  Attributes: {{ entity.attributes }}
  {%- endif %}
{%- endfor %}
```

## 5. Voir tous les boutons

```yaml
{%- set child_name = "maceo_collin" %}

=== BUTTONS ===
{%- for entity in states.button %}
  {%- if child_name in entity.entity_id %}

{{ entity.name }}:
  State: {{ entity.state }}
  Attributes: {{ entity.attributes }}
  {%- endif %}
{%- endfor %}
```

## 6. Voir TOUTES les entités liées à l'enfant

```yaml
{%- set child_name = "maceo_collin" %}

=== TOUTES LES ENTITÉS ===

SENSORS:
{%- for entity in states.sensor %}
  {%- if child_name in entity.entity_id %}
- {{ entity.entity_id }}: {{ entity.state }}
  {%- endif %}
{%- endfor %}

BINARY SENSORS:
{%- for entity in states.binary_sensor %}
  {%- if child_name in entity.entity_id %}
- {{ entity.entity_id }}: {{ entity.state }}
  {%- endif %}
{%- endfor %}

SWITCHES:
{%- for entity in states.switch %}
  {%- if child_name in entity.entity_id %}
- {{ entity.entity_id }}: {{ entity.state }}
  {%- endif %}
{%- endfor %}

BUTTONS:
{%- for entity in states.button %}
  {%- if child_name in entity.entity_id %}
- {{ entity.entity_id }}: {{ entity.state }}
  {%- endif %}
{%- endfor %}
```

## Note importante

Pour voir les données complètes de remaining_minutes, bedtime_window, etc., regarde SURTOUT les attributs de ces sensors :
- `sensor.DEVICE_NAME_screen_time_remaining` (un par device)
- `sensor.DEVICE_NAME_next_restriction` (un par device)
- `binary_sensor.DEVICE_NAME_bedtime_active` (un par device)
- `binary_sensor.DEVICE_NAME_schooltime_active` (un par device)
