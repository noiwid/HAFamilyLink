# Debug Device Entities - Copie tout et colle dans HA Template Editor

```yaml
{%- set devices = ["galaxy_tab_maceo", "sm_s916b"] %}

=== ENTITÉS PAR DEVICE ===

{%- for device in devices %}

DEVICE: {{ device | upper }}
==================

BINARY SENSORS:
  Bedtime Active: {{ states('binary_sensor.' + device + '_bedtime_active') }}
  School Time Active: {{ states('binary_sensor.' + device + '_school_time_active') }}
  Daily Limit Reached: {{ states('binary_sensor.' + device + '_daily_limit_reached') }}

SENSORS:
  Screen Time Remaining: {{ states('sensor.' + device + '_screen_time_remaining') }}
    Attributs: {{ state_attr('sensor.' + device + '_screen_time_remaining', '') }}

  Next Restriction: {{ states('sensor.' + device + '_next_restriction') }}
    Attributs: {{ state_attr('sensor.' + device + '_next_restriction', '') }}

BUTTONS:
  +15min: {{ states('button.' + device + '_15min') }}
  +30min: {{ states('button.' + device + '_30min') }}
  +60min: {{ states('button.' + device + '_60min') }}

{%- endfor %}
```
