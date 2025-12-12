# Water Flow Meter - Home Assistant Custom Component

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)

Custom komponenta pro Home Assistant pro měření průtoku vody na základě pulzních senzorů.

## Funkce

✨ **8 senzorů pro kompletní monitorování:**

### 📊 Senzory průtoku
- 🚰 **Průtok vody (L/min)** - aktuální rychlost průtoku v litrech za minutu
- 🌊 **Průtok vody (L/h)** - průtok v litrech za hodinu
- 💨 **Průtok vody (L/s)** - průtok v litrech za sekundu
- ⚡ **Pulzy za minutu** - počet pulzů detekovaných za minutu

### 💧 Senzory objemu
- 💧 **Celkový objem** (litry) - kumulativní spotřeba vody

### 🔍 Diagnostické senzory
- ⏱️ **Čas od posledního pulzu** - jak dlouho neprošel žádný pulz
- 📏 **Průměrná doba mezi pulzy** - průměrný interval mezi pulzy
- 🕐 **Uptime komponenty** - jak dlouho komponenta běží

### 📈 Pokročilé statistiky (atributy)
- **Maximální průtok dnes** - nejvyšší naměřený průtok za dnešní den
- **Průměrný průtok dnes** - průměrný průtok za dnešní den
- **Celková doba průtoku dnes** - jak dlouho dnes voda tekla

## Hlavní vlastnosti

- ⚙️ **Konfigurovatelné přes UI** - snadné nastavení bez editace YAML
- 🎯 **Výběr zdrojového senzoru** - připojte jakýkoliv sensor, counter nebo input_number
- 🔧 **Nastavitelné parametry:**
  - Počet pulzů na litr (podle vašeho průtokoměru)
  - Časové okno pro výpočet průtoku (10-600 sekund)
- 🌍 **Vícejazyčné** - podporuje češtinu a angličtinu
- 📊 **Kompatibilní s Energy Dashboard** - total volume sensor je připraven pro HA Energy
- 📈 **Detailní statistiky** - sledování denních maxim, průměrů a dob průtoku

## Instalace

### Manuální instalace

1. Zkopírujte složku `custom_components/water_flow_meter` do složky `custom_components` ve vaší Home Assistant instalaci:
   ```
   <config>/custom_components/water_flow_meter/
   ```

2. Restartujte Home Assistant

### HACS (doporučeno)

1. Otevřete HACS
2. Přejděte na "Integrations"
3. Klikněte na tlačítko s třemi tečkami v pravém horním rohu
4. Vyberte "Custom repositories"
5. Přidejte URL tohoto repozitáře
6. Vyberte kategorii "Integration"
7. Klikněte na "ADD"
8. Najděte "Water Flow Meter" v seznamu a nainstalujte
9. Restartujte Home Assistant

## Konfigurace

### Přes UI (doporučeno)

1. Přejděte na **Nastavení** → **Zařízení a služby**
2. Klikněte na **+ PŘIDAT INTEGRACI**
3. Vyhledejte **"Water Flow Meter"**
4. Vyplňte konfigurační formulář:
   - **Zdrojový pulzní senzor**: Vyberte entitu, která počítá pulzy (sensor, counter nebo input_number - např. `sensor.water_pulse_counter`, `counter.water_pulses`)
   - **Pulzy na litr**: Zadejte, kolik pulzů odpovídá jednomu litru (např. 1.0 pro typické průtokoměry)
   - **Časové okno**: Časový interval pro výpočet průtoku (výchozí 60 sekund)

### Příklad zdrojového senzoru (ESPHome)

Pokud používáte ESPHome s pulse counter:

```yaml
sensor:
  - platform: pulse_counter
    pin: GPIO13
    name: "Water Pulse Counter"
    unit_of_measurement: "pulses"
    count_mode:
      rising_edge: INCREMENT
      falling_edge: DISABLE
    update_interval: 1s
    total:
      name: "Water Total Pulses"
      unit_of_measurement: "pulses"
```

### Použití s Home Assistant Counter

Pokud chcete použít vestavěnou HA counter entitu (např. pro testování):

```yaml
# configuration.yaml
counter:
  water_pulses:
    name: Water Pulse Counter
    initial: 0
    step: 1
    icon: mdi:counter

# Automatizace pro inkrementaci (příklad s binary senzorem)
automation:
  - alias: "Increment water pulse counter"
    trigger:
      - platform: state
        entity_id: binary_sensor.water_flow_pulse
        to: "on"
    action:
      - service: counter.increment
        target:
          entity_id: counter.water_pulses
```

Pak použijte `counter.water_pulses` jako zdrojový senzor v konfiguraci Water Flow Meter.

## Jak to funguje

### Detekce pulzů

Komponenta sleduje změny hodnoty zdrojového senzoru. Když se hodnota zvýší, jsou detekovány nové pulzy.

### Výpočet průtoku

Průtok je vypočítán pomocí **sliding window** algoritmu:

1. Komponenta ukládá časy všech pulzů v nastaveném časovém okně
2. Počítá průměrný počet pulzů za minutu
3. Přepočítá na litry za minutu podle parametru "pulzy na litr"

**Vzorec:**
```
pulzy_za_minutu = (počet_pulzů_v_okně / délka_okna_v_sekundách) × 60
litry_za_minutu = pulzy_za_minutu / pulzy_na_litr
```

### Výpočet celkového objemu

Celkový objem je kumulativní součet všech detekovaných pulzů, přepočtený na litry.

**Vzorec:**
```
celkový_objem_litrů = celkový_počet_pulzů / pulzy_na_litr
```

## Příklady použití

### Automatizace - upozornění na vysokou spotřebu

```yaml
automation:
  - alias: "Upozornění na vysoký průtok vody"
    trigger:
      - platform: numeric_state
        entity_id: sensor.water_flow_rate_water_pulse_counter
        above: 20  # 20 litrů za minutu
        for:
          minutes: 5
    action:
      - service: notify.mobile_app
        data:
          title: "⚠️ Vysoký průtok vody!"
          message: "Průtok vody přesahuje 20 l/min už 5 minut. Kontrolujte možný únik."
```

### Denní statistiky pomocí Utility Meter

```yaml
utility_meter:
  water_daily:
    source: sensor.water_total_volume_water_pulse_counter
    cycle: daily

  water_monthly:
    source: sensor.water_total_volume_water_pulse_counter
    cycle: monthly
```

### Lovelace karta

```yaml
type: entities
title: Spotřeba vody
entities:
  - entity: sensor.water_flow_rate_water_pulse_counter
    name: Aktuální průtok (L/min)
  - entity: sensor.water_flow_rate_hourly_water_pulse_counter
    name: Průtok (L/h)
  - entity: sensor.water_flow_rate_secondary_water_pulse_counter
    name: Průtok (L/s)
  - entity: sensor.water_pulse_rate_water_pulse_counter
    name: Pulzy za minutu
  - entity: sensor.water_total_volume_water_pulse_counter
    name: Celková spotřeba
  - entity: sensor.water_daily
    name: Dnes
  - entity: sensor.water_monthly
    name: Tento měsíc
```

### Využití diagnostických senzorů

```yaml
# Upozornění když voda neteče příliš dlouho (možný problém)
automation:
  - alias: "Diagnostika - žádné pulzy"
    trigger:
      - platform: numeric_state
        entity_id: sensor.water_time_since_last_pulse_water_pulse_counter
        above: 86400  # 24 hodin
    action:
      - service: notify.mobile_app
        data:
          title: "ℹ️ Diagnostika vodoměru"
          message: "Za posledních 24 hodin nebyl detekován žádný pulz. Zkontrolujte senzor."

# Monitorování průměrného intervalu pulzů
template:
  - sensor:
      - name: "Water Flow Health"
        state: >
          {% set interval = states('sensor.water_average_pulse_interval_water_pulse_counter') | float(0) %}
          {% if interval == 0 %}unknown
          {% elif interval < 10 %}vysoký průtok
          {% elif interval < 60 %}normální
          {% else %}nízký průtok{% endif %}
```

## Detailní popis senzorů

### 📊 Senzory průtoku

#### Water Flow Rate (L/min)
- **Entity ID**: `sensor.water_flow_rate_*`
- **Jednotka**: L/min (litry za minutu)
- **Účel**: Hlavní senzor průtoku, optimální pro domácí použití
- **Atributy**:
  - `max_flow_today` - maximální průtok za dnešní den
  - `average_flow_today` - průměrný průtok za dnešní den
  - `total_flow_duration_today` - celková doba průtoku v sekundách

#### Water Flow Rate Hourly (L/h)
- **Entity ID**: `sensor.water_flow_rate_hourly_*`
- **Jednotka**: L/h (litry za hodinu)
- **Účel**: Vhodný pro dlouhodobější sledování nebo pomalejší průtoky

#### Water Flow Rate Secondary (L/s)
- **Entity ID**: `sensor.water_flow_rate_secondary_*`
- **Jednotka**: L/s (litry za sekundu)
- **Účel**: Ideální pro rychlé průtoky nebo průmyslové aplikace

#### Water Pulse Rate
- **Entity ID**: `sensor.water_pulse_rate_*`
- **Jednotka**: pulses/min (pulzy za minutu)
- **Účel**: Zobrazuje surový počet pulzů, užitečné pro diagnostiku senzoru

### 💧 Senzor objemu

#### Water Total Volume
- **Entity ID**: `sensor.water_total_volume_*`
- **Jednotka**: L (litry)
- **Device Class**: water (kompatibilní s Energy Dashboard)
- **State Class**: total_increasing
- **Účel**: Celková kumulativní spotřeba vody od spuštění komponenty

### 🔍 Diagnostické senzory

#### Water Time Since Last Pulse
- **Entity ID**: `sensor.water_time_since_last_pulse_*`
- **Jednotka**: seconds (sekundy)
- **Účel**: Monitorování aktivity senzoru, detekce výpadků
- **Použití**: Upozornění když senzor dlouho nedetekuje pulzy

#### Water Average Pulse Interval
- **Entity ID**: `sensor.water_average_pulse_interval_*`
- **Jednotka**: seconds (sekundy)
- **Účel**: Průměrný čas mezi pulzy (z posledních 100 pulzů)
- **Použití**: Analýza vzorců spotřeby, kalibrace

#### Water Meter Uptime
- **Entity ID**: `sensor.water_meter_uptime_*`
- **Jednotka**: seconds (sekundy)
- **Účel**: Sledování doby běhu komponenty
- **Atributy**:
  - `start_time` - čas spuštění komponenty
  - `uptime_formatted` - formátovaný uptime (např. "5d 3h 42m")

## Populární průtokoměry

| Model | Pulzy na litr | Poznámka |
|-------|---------------|----------|
| YF-S201 | 7.5 | Běžný průtokoměr 1/2" |
| YF-B6 | 6.6 | Průtokoměr s větším průměrem |
| Standardní vodoměr | 1.0 | Většina mechanických vodoměrů - 1 pulz = 1 litr |
| Custom | ? | Zkontrolujte dokumentaci vašeho průtokoměru |

💡 **Tip:** Hodnotu "pulzy na litr" můžete později upravit v nastavení integrace bez nutnosti rekonfigurace.

## Řešení problémů

### Senzor nedetekuje pulzy

1. Ověřte, že zdrojový senzor správně funguje a aktualizuje svou hodnotu
2. Zkontrolujte logy Home Assistant: `Settings → System → Logs`
3. Ujistěte se, že hodnota senzoru je numerická (ne "unknown" nebo "unavailable")

### Průtok je příliš vysoký/nízký

- Upravte parametr **"Pulzy na litr"** podle specifikace vašeho průtokoměru
- Zkontrolujte, zda zdrojový senzor správně počítá pulzy

### Senzor zobrazuje 0 i při průtoku

- Zvyšte **"Časové okno"** na vyšší hodnotu (např. 120 sekund)
- Ověřte, že pulzy jsou správně detekovány zdrojovým senzorem

## Technické detaily

### Senzory

Komponenta vytváří tři senzory:

1. **`sensor.water_flow_rate_*`**
   - Jednotka: L/min (litry za minutu)
   - State class: `measurement`
   - Device class: `volume_flow_rate`

2. **`sensor.water_pulse_rate_*`**
   - Jednotka: pulses/min (pulzy za minutu)
   - State class: `measurement`

3. **`sensor.water_total_volume_*`**
   - Jednotka: L (litry)
   - State class: `total_increasing`
   - Device class: `water`
   - ✅ Kompatibilní s Energy Dashboard

### Atributy

Každý senzor obsahuje dodatečné atributy:

- `last_pulse_time`: Čas posledního detekovaného pulzu
- `pulse_count`: Aktuální počet pulzů (v okně nebo celkový)
- `pulses_per_liter`: Nastavený poměr pulzů na litr

## Odkazy

**Užitečné zdroje:**

- [Home Assistant Water Integration Docs](https://www.home-assistant.io/docs/energy/water/)
- [ESPHome Pulse Counter](https://esphome.io/components/sensor/pulse_counter/)
- [HA Community - Water Flow Meter Discussion](https://community.home-assistant.io/t/water-flow-meter-with-pulse-counter-daily-usage/136319)
- [Build Water Usage Sensor Tutorial](https://www.pieterbrinkman.com/2022/02/02/build-a-cheap-water-usage-sensor-using-esphome-home-assistant-and-a-proximity-sensor/)

## Podpora

Pokud máte problém nebo nápad na vylepšení:

1. Zkontrolujte [Issues](../../issues) jestli už problém není reportován
2. Vytvořte nový Issue s detailním popisem
3. Přiložte relevantní část logů z Home Assistant

## Licence

MIT License - volně použitelné pro osobní i komerční účely.

## Autor

Vytvořeno s ❤️ pro Home Assistant komunitu

---

**⭐ Pokud se vám komponenta líbí, dejte repozitáři hvězdičku!**
