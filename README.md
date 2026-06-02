# M600 G-code intervaly

Jednoduchá Streamlit appka pro výpočet intervalů mezi `M600` výměnami filamentu v G-code z OrcaSliceru.

## Lokální spuštění

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Co umí

- Nahraje `.gcode`
- Najde všechny `M600`
- Spočítá intervaly podle `M73 R...`
- Vypíše časy mezi výměnami
- Vygeneruje upravený G-code s `NEXT_CHANGE_MIN=...`

## G-code příklad

Z:

```gcode
M600 NEXT=1 COLOR=#A2D634
```

udělá:

```gcode
M600 NEXT=1 COLOR=#A2D634 NEXT_CHANGE_MIN=27
```
