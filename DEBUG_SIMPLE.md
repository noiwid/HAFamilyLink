# Template de Debug Simple - Copie tout et colle dans HA Template Editor

```yaml
{%- set child_name = "maceo_collin" %}

=== RÉSUMÉ COMPLET ===

TOTAL SENSORS: {{ states.sensor | selectattr('entity_id', 'search', child_name) | list | count }}
TOTAL BINARY SENSORS: {{ states.binary_sensor | selectattr('entity_id', 'search', child_name) | list | count }}
TOTAL SWITCHES: {{ states.switch | selectattr('entity_id', 'search', child_name) | list | count }}
TOTAL BUTTONS: {{ states.button | selectattr('entity_id', 'search', child_name) | list | count }}

=== TOUS LES SENSORS ===
{%- for entity in states.sensor | selectattr('entity_id', 'search', child_name) %}
{{ loop.index }}. {{ entity.entity_id }}
   State: {{ entity.state }}
   {%- if 'child_id' in entity.attributes %}
   Child ID: {{ entity.attributes.child_id }}
   {%- endif %}
   {%- if 'device_id' in entity.attributes %}
   Device ID: {{ entity.attributes.device_id }}
   {%- endif %}
   {%- if 'device_name' in entity.attributes %}
   Device Name: {{ entity.attributes.device_name }}
   {%- endif %}
   {%- if 'total_allowed_minutes' in entity.attributes %}
   Total Allowed: {{ entity.attributes.total_allowed_minutes }}
   {%- endif %}
   {%- if 'used_minutes' in entity.attributes %}
   Used Minutes: {{ entity.attributes.used_minutes }}
   {%- endif %}
   {%- if 'remaining_minutes' in entity.attributes %}
   Remaining: {{ entity.attributes.remaining_minutes }}
   {%- endif %}
   {%- if 'daily_limit_enabled' in entity.attributes %}
   Daily Limit Enabled: {{ entity.attributes.daily_limit_enabled }}
   {%- endif %}
   {%- if 'daily_limit_minutes' in entity.attributes %}
   Daily Limit Minutes: {{ entity.attributes.daily_limit_minutes }}
   {%- endif %}
{%- endfor %}

=== TOUS LES BINARY SENSORS ===
{%- for entity in states.binary_sensor | selectattr('entity_id', 'search', child_name) %}
{{ loop.index }}. {{ entity.entity_id }}
   State: {{ entity.state }}
   Device Class: {{ entity.attributes.device_class if 'device_class' in entity.attributes else 'none' }}
   {%- if 'device_id' in entity.attributes %}
   Device ID: {{ entity.attributes.device_id }}
   {%- endif %}
   {%- if 'device_name' in entity.attributes %}
   Device Name: {{ entity.attributes.device_name }}
   {%- endif %}
{%- endfor %}

=== TOUS LES SWITCHES ===
{%- for entity in states.switch | selectattr('entity_id', 'search', child_name) %}
{{ loop.index }}. {{ entity.entity_id }}
   State: {{ entity.state }}
   {%- if 'device_id' in entity.attributes %}
   Device ID: {{ entity.attributes.device_id }}
   {%- endif %}
{%- endfor %}

=== TOUS LES BUTTONS ===
{%- for entity in states.button | selectattr('entity_id', 'search', child_name) %}
{{ loop.index }}. {{ entity.entity_id }}
   State: {{ entity.state }}
   {%- if 'device_id' in entity.attributes %}
   Device ID: {{ entity.attributes.device_id }}
   {%- endif %}
   {%- if 'device_name' in entity.attributes %}
   Device Name: {{ entity.attributes.device_name }}
   {%- endif %}
{%- endfor %}

=== ANALYSE ===
Problème détecté: {{ "AUCUN sensor par device trouvé !" if (states.sensor | selectattr('entity_id', 'search', child_name) | selectattr('attributes.device_id', 'defined') | list | count) == 0 else "Sensors par device OK" }}
Problème détecté: {{ "AUCUN binary_sensor par device trouvé !" if (states.binary_sensor | selectattr('entity_id', 'search', child_name) | list | count) == 0 else "Binary sensors par device OK" }}
Problème détecté: {{ "AUCUN bouton trouvé !" if (states.button | selectattr('entity_id', 'search', child_name) | list | count) == 0 else "Boutons OK" }}
```
