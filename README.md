# Water Flow Meter - Home Assistant Custom Component

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)

Custom komponenta pro Home Assistant pro měření průtoku vody na základě pulzních senzorů.

## Funkce

✨ **13 senzorů pro kompletní monitorování:**

### 📊 Senzory průtoku (Sliding Window)
- 🚰 **Průtok vody (L/min)** - průměrný průtok za časové okno
- 🌊 **Průtok vody (L/h)** - průtok v litrech za hodinu
- 💨 **Průtok vody (L/s)** - průtok v litrech za sekundu
- ⚡ **Pulzy za minutu** - průměr pulzů za časové okno

### ⚡ Senzory okamžitého průtoku (Real-time)
- ⚡ **Okamžitý průtok (L/min)** - vypočteno z času mezi pulzy
- 🔥 **Okamžité pulzy/min** - aktuální frekvence pulzů

### 💧 Senzory objemu
- 💧 **Celkový objem** (litry) - kumulativní spotřeba vody s persistencí

### 🤖 Automatizace & Monitoring
- 🔄 **Is Flowing** (binary sensor) - ON/OFF stav průtoku
- 🔢 **Počet startů dnes** - kolikrát začala téct voda
- ⏱️ **Celkový čas běhu dnes** - jak dlouho dnes voda tekla

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
  - Časové okno pro výpočet průtoku (0-3600 sekund)
  - **0 = neustálý průtok** (pro oběhová čerpadla)
- 💾 **Persistence** - data se zachovávají při restartu HA
- 🎛️ **Služby (Services)** - reset, kalibrace a správa dat
- 📱 **Device Registry** - všechny senzory seskupené pod jedno zařízení
- 🌍 **Vícejazyčné** - podporuje češtinu a angličtinu
- 📊 **Kompatibilní s Energy Dashboard** - total volume sensor je připraven pro HA Energy
- 📈 **Detailní statistiky** - sledování denních maxim, průměrů a dob průtoku
- 🤖 **Binary sensor** - snadné triggery v automatizacích

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
   - **Zdrojový pulzní senzor**: Vyberte entitu, která počítá pulzy (sensor, counter nebo input_number)
   - **Pulzy na litr**: Zadejte, kolik pulzů odpovídá jednomu litru (např. 1.0 pro typické průtokoměry)
   - **Časové okno**: Časový interval pro výpočet průtoku
     - **60-3600** = sliding window (průměr za X sekund)
     - **0** = neustálý průtok od startu (ideální pro oběhová čerpadla)

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

#### Sliding Window režim (časové okno > 0)

Průtok je vypočítán pomocí **sliding window** algoritmu:

1. Komponenta ukládá časy všech pulzů v nastaveném časovém okně
2. Počítá průměrný počet pulzů za minutu
3. Přepočítá na litry za minutu podle parametru "pulzy na litr"

**Vzorec:**
```
pulzy_za_minutu = (počet_pulzů_v_okně / délka_okna_v_sekundách) × 60
litry_za_minutu = pulzy_za_minutu / pulzy_na_litr
```

#### Continuous Flow režim (časové okno = 0)

Pro oběhová čerpadla, kde voda teče neustále:

**Vzorec:**
```
průměrný_průtok = celkový_počet_pulzů / celkový_čas_od_startu
```

Hodnota se nemění dokud se nerestartuje integrace.

#### Okamžitý průtok (Instantaneous)

Vypočítán z času mezi posledními 2-3 pulzy:

**Vzorec:**
```
litry_za_minutu = (1 / pulzy_na_litr) / interval_mezi_pulzy × 60
```

Rychle reaguje na změny průtoku, ideální pro monitoring v reálném čase.

### Výpočet celkového objemu

Celkový objem je kumulativní součet všech detekovaných pulzů, přepočtený na litry.

**Vzorec:**
```
celkový_objem_litrů = celkový_počet_pulzů / pulzy_na_litr
```

## Příklady použití

### Automatizace - upozornění na dlouhý běh vody

```yaml
automation:
  - alias: "Varování - voda teče moc dlouho"
    trigger:
      - platform: state
        entity_id: binary_sensor.water_is_flowing_xxx
        to: 'on'
        for:
          minutes: 30
    action:
      - service: notify.mobile_app
        data:
          title: "⚠️ Voda teče moc dlouho!"
          message: "Voda teče už 30 minut! Možný únik nebo zapomenutý kohoutek?"
```

### Detekce problému čerpadla (moc časté starty)

```yaml
automation:
  - alias: "Varování - moc startů čerpadla"
    trigger:
      - platform: numeric_state
        entity_id: sensor.water_flow_starts_today_xxx
        above: 50
    action:
      - service: notify.mobile_app
        data:
          message: "Čerpadlo startovalo {{states('sensor.water_flow_starts_today_xxx')}}× dnes. Zkontroluj únik!"
```

### Automatizace zapnutí čerpadla podle průtoku

```yaml
automation:
  - alias: "Zapni čerpadlo při průtoku"
    trigger:
      - platform: state
        entity_id: binary_sensor.water_is_flowing_xxx
        to: 'on'
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.water_pump

  - alias: "Vypni čerpadlo po zastavení průtoku"
    trigger:
      - platform: state
        entity_id: binary_sensor.water_is_flowing_xxx
        to: 'off'
        for:
          seconds: 10
    action:
      - service: switch.turn_off
        target:
          entity_id: switch.water_pump
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

### Lovelace karta - kompletní přehled

```yaml
type: entities
title: Spotřeba vody
entities:
  # Aktuální stav
  - type: section
    label: "Aktuální stav"
  - entity: binary_sensor.water_is_flowing_xxx
    name: Voda teče
  - entity: sensor.water_instantaneous_flow_rate_xxx
    name: Okamžitý průtok

  # Průtoky
  - type: section
    label: "Průtoky"
  - entity: sensor.water_flow_rate_xxx
    name: Průměr (60s) L/min
  - entity: sensor.water_flow_rate_hourly_xxx
    name: Průtok L/h
  - entity: sensor.water_flow_rate_secondary_xxx
    name: Průtok L/s

  # Spotřeba
  - type: section
    label: "Spotřeba"
  - entity: sensor.water_total_volume_xxx
    name: Celková spotřeba
  - entity: sensor.water_daily
    name: Dnes
  - entity: sensor.water_monthly
    name: Tento měsíc

  # Denní statistiky
  - type: section
    label: "Statistiky dnes"
  - entity: sensor.water_flow_starts_today_xxx
    name: Počet startů
  - entity: sensor.water_running_time_today_xxx
    name: Celkový čas běhu
```

## Detailní popis senzorů

### 📊 Senzory průtoku (Sliding Window)

#### Water Flow Rate (L/min)
- **Entity ID**: `sensor.water_flow_rate_*`
- **Jednotka**: L/min (litry za minutu)
- **Účel**: Hlavní senzor průtoku, průměr za časové okno
- **Atributy**:
  - `max_flow_today` - maximální průtok za dnešní den
  - `average_flow_today` - průměrný průtok za dnešní den
  - `total_flow_duration_today` - celková doba průtoku v sekundách

#### Water Flow Rate Hourly (L/h)
- **Entity ID**: `sensor.water_flow_rate_hourly_*`
- **Jednotka**: L/h (litry za hodinu)
- **Účel**: Vhodný pro dlouhodobější sledování

#### Water Flow Rate Secondary (L/s)
- **Entity ID**: `sensor.water_flow_rate_secondary_*`
- **Jednotka**: L/s (litry za sekundu)
- **Účel**: Ideální pro rychlé průtoky

#### Water Pulse Rate
- **Entity ID**: `sensor.water_pulse_rate_*`
- **Jednotka**: pulses/min (pulzy za minutu)
- **Účel**: Zobrazuje průměr pulzů, užitečné pro diagnostiku

### ⚡ Senzory okamžitého průtoku

#### Water Instantaneous Flow Rate (L/min)
- **Entity ID**: `sensor.water_instantaneous_flow_rate_*`
- **Jednotka**: L/min
- **Účel**: Okamžitý průtok vypočtený z času mezi pulzy
- **Výhody**: Rychle reaguje na změny, funguje i když voda teče celý den

#### Water Instantaneous Pulse Rate
- **Entity ID**: `sensor.water_instantaneous_pulse_rate_*`
- **Jednotka**: pulses/min
- **Účel**: Okamžitá frekvence pulzů

### 💧 Senzor objemu

#### Water Total Volume
- **Entity ID**: `sensor.water_total_volume_*`
- **Jednotka**: L (litry)
- **Device Class**: water (kompatibilní s Energy Dashboard)
- **State Class**: total_increasing
- **Účel**: Celková kumulativní spotřeba vody od spuštění komponenty
- **Persistence**: ✅ Zachovává se při restartu

### 🤖 Automatizace & Monitoring

#### Water Is Flowing (Binary Sensor)
- **Entity ID**: `binary_sensor.water_is_flowing_*`
- **Device Class**: running
- **Stav**: `ON` když průtok > 0.1 L/min
- **Atributy**:
  - `current_flow_duration` - jak dlouho aktuálně teče (sekundy)
- **Použití**: Triggery v automatizacích

#### Water Flow Starts Today
- **Entity ID**: `sensor.water_flow_starts_today_*`
- **Jednotka**: starts
- **Účel**: Počet přechodů z "neteče" → "teče"
- **Reset**: Automaticky o půlnoci
- **Použití**: Detekce úniků (moc častý průtok)

#### Water Running Time Today
- **Entity ID**: `sensor.water_running_time_today_*`
- **Jednotka**: seconds
- **Účel**: Celková doba kdy voda tekla dnes
- **Atributy**:
  - `formatted` - "5h 23m"
  - `hours` - 5.38
- **Použití**: Sledování doby provozu čerpadla

### 🔍 Diagnostické senzory

#### Water Time Since Last Pulse
- **Entity ID**: `sensor.water_time_since_last_pulse_*`
- **Jednotka**: seconds (sekundy)
- **Účel**: Monitorování aktivity senzoru, detekce výpadků

#### Water Average Pulse Interval
- **Entity ID**: `sensor.water_average_pulse_interval_*`
- **Jednotka**: seconds (sekundy)
- **Účel**: Průměrný čas mezi pulzy (z posledních 100 pulzů)

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

## 🎛️ Služby (Services)

Komponenta poskytuje tři služby pro ovládání a kalibraci:

### Reset Total Volume

Resetuje celkový objem vody na nulu.

```yaml
service: water_flow_meter.reset_total_volume
target:
  entity_id: sensor.water_total_volume_water_pulse_counter
```

**Použití**: Když chcete začít měřit spotřebu od nuly.

### Set Total Volume

Nastaví celkový objem na konkrétní hodnotu (kalibrace).

```yaml
service: water_flow_meter.set_total_volume
data:
  volume: 1500.5  # litrů
target:
  entity_id: sensor.water_total_volume_water_pulse_counter
```

**Použití**: Pro kalibraci - když známe skutečnou spotřebu z fyzického vodoměru.

### Reset Daily Statistics

Resetuje denní statistiky (max průtok, průměr, dobu průtoku, počet startů).

```yaml
service: water_flow_meter.reset_daily_statistics
target:
  entity_id: sensor.water_flow_rate_water_pulse_counter
```

**Použití**: Manuální reset statistik (normálně se resetují o půlnoci automaticky).

## 💾 Persistence (Zachování dat)

Komponenta automaticky ukládá a obnovuje data při restartu Home Assistant:

### Co se zachovává:
- ✅ **Celkový objem vody** - neztratíte data o spotřebě
- ✅ **Denní statistiky** - max průtok, průměr, doba průtoku, počet startů
- ✅ **Stav průtoku** - is_flowing
- ✅ **Čas spuštění** - pro správný uptime
- ✅ **Poslední pulz** - pro kontinuitu měření

Data jsou uložena v atributech senzorů a automaticky se obnovují po:
- Restartu Home Assistant
- Reload integrace
- Aktualizaci komponenty

## 📱 Device Registry

Všechny senzory jsou seskupené pod jedno "zařízení" v Home Assistant:

```
Water Flow Meter (sensor.water_pulse_counter)
├── Flow Rate (L/min)
├── Flow Rate Hourly (L/h)
├── Flow Rate Secondary (L/s)
├── Pulse Rate (pulses/min)
├── Instantaneous Flow Rate (L/min)
├── Instantaneous Pulse Rate (pulses/min)
├── Total Volume (L)
├── Is Flowing (binary)
├── Flow Starts Today (starts)
├── Running Time Today (seconds)
├── Time Since Last Pulse (s)
├── Average Pulse Interval (s)
└── Meter Uptime (s)
```

**Výhody**:
- Lepší organizace v UI
- Snadná správa všech senzorů najednou
- Přehledné zobrazení v Nastavení → Zařízení a služby

## Režimy použití

### 🏠 Domácí spotřeba (běžné použití)

**Nastavení:**
- Časové okno: **60 sekund**
- Pulzy na litr: podle průtokoměru

**Senzory k použití:**
- `sensor.water_flow_rate_*` (L/min)
- `sensor.water_total_volume_*`
- `binary_sensor.water_is_flowing_*`

### 🔄 Oběhové čerpadlo

**Nastavení:**
- Časové okno: **0** (continuous flow)
- Pulzy na litr: podle průtokoměru

**Senzory k použití:**
- `sensor.water_flow_rate_*` - stabilní průměr od startu
- `sensor.water_instantaneous_flow_rate_*` - okamžitý průtok
- `sensor.water_running_time_today_*` - čas provozu
- `sensor.water_flow_starts_today_*` - počet cyklů

### ⚡ Real-time monitoring

**Nastavení:**
- Časové okno: libovolné

**Senzory k použití:**
- `sensor.water_instantaneous_flow_rate_*` - rychlá reakce
- `binary_sensor.water_is_flowing_*` - okamžité triggery

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
- Zkuste použít **Instantaneous Flow Rate** senzor

### L/h a L/s neodpovídají L/min

Správné převody:
- **3 L/min** = **180 L/h** = **0.05 L/s** ✓
- **6 L/min** = **360 L/h** = **0.1 L/s** ✓

Pokud vidíte jiné hodnoty, restartujte integraci.

## Technické detaily

### State Classes

- **measurement** - okamžité hodnoty (průtoky)
- **total_increasing** - rostoucí celkové hodnoty (objem, čas běhu, počet startů)

### Device Classes

- **volume_flow_rate** - průtoky (L/min, L/h, L/s)
- **water** - objem vody (kompatibilní s Energy Dashboard)
- **duration** - časy (uptime, running time)
- **running** - binární stav běhu

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
