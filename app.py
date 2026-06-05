import html
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import streamlit as st


PRAGUE_TZ = ZoneInfo("Europe/Prague")

M73_RE = re.compile(r"\bM73\b.*?\bR(\d+)\b")
M600_RE = re.compile(r"^\s*M600\b", re.IGNORECASE)
COLOR_RE = re.compile(r"\bCOLOR=([#A-Fa-f0-9]+)")
NEXT_RE = re.compile(r"\bNEXT=([0-9-]+)")


def fmt_minutes(minutes: Optional[int]) -> str:
    if minutes is None or minutes < 0:
        return "?"

    hours, mins = divmod(int(minutes), 60)

    if hours and mins:
        return f"{hours} h {mins} min"
    if hours:
        return f"{hours} h"
    return f"{mins} min"


def parse_gcode_text(text: str):
    lines = text.splitlines()

    total_remaining: Optional[int] = None
    last_remaining: Optional[int] = None
    events = []

    for idx, line in enumerate(lines):
        m73 = M73_RE.search(line)
        if m73:
            last_remaining = int(m73.group(1))
            if total_remaining is None:
                total_remaining = last_remaining

        if M600_RE.search(line):
            color = COLOR_RE.search(line)
            nxt = NEXT_RE.search(line)

            events.append(
                {
                    "line_index": idx,
                    "line_number": idx + 1,
                    "line": line,
                    "remaining": last_remaining,
                    "color": color.group(1) if color else "",
                    "next": nxt.group(1) if nxt else "",
                }
            )

    if total_remaining is None:
        raise ValueError(
            "V souboru jsem nenašel M73 R... časové údaje. "
            "Bez nich nejde spolehlivě spočítat časy."
        )

    prev_elapsed = 0

    for i, event in enumerate(events):
        if event["remaining"] is None:
            event["elapsed"] = None
            event["interval_from_prev"] = None
        else:
            event["elapsed"] = total_remaining - event["remaining"]
            event["interval_from_prev"] = event["elapsed"] - prev_elapsed
            prev_elapsed = event["elapsed"]

        if (
            i + 1 < len(events)
            and event["remaining"] is not None
            and events[i + 1]["remaining"] is not None
        ):
            event["next_change_min"] = event["remaining"] - events[i + 1]["remaining"]
        else:
            event["next_change_min"] = -1

    return lines, total_remaining, events


def make_modified_gcode(lines: list[str], events: list[dict]) -> str:
    out_lines = list(lines)

    for event in events:
        idx = event["line_index"]
        line = out_lines[idx]

        line = re.sub(r"\s+NEXT_CHANGE_MIN=-?\d+", "", line)
        line = f"{line} NEXT_CHANGE_MIN={event['next_change_min']}"
        out_lines[idx] = line

    return "\n".join(out_lines) + "\n"


def normalize_hex_color(hex_color: str) -> str:
    if not hex_color:
        return ""

    color = hex_color.strip()
    if not color.startswith("#"):
        color = f"#{color}"

    if not re.fullmatch(r"#[A-Fa-f0-9]{6}", color):
        return ""

    return color.upper()


def build_color_badge(hex_color: str) -> str:
    color = normalize_hex_color(hex_color)
    if not color:
        return ""

    border = "#999" if color == "#FFFFFF" else "#888"

    return (
        f'<span style="display:inline-flex;align-items:center;gap:8px;">'
        f'<span style="display:inline-block;width:18px;height:18px;'
        f'background:{color};border:1px solid {border};border-radius:4px;'
        f'vertical-align:middle;"></span>'
        f'<code>{color}</code>'
        f'</span>'
    )


def build_intervals_table_html(rows: list[dict]) -> str:
    table_html = """
    <table style="width:100%; border-collapse:collapse; font-family:sans-serif; font-size:14px;">
      <thead>
        <tr>
          <th style="text-align:left; padding:8px; border-bottom:1px solid #ddd;">Úsek</th>
          <th style="text-align:left; padding:8px; border-bottom:1px solid #ddd;">Interval</th>
          <th style="text-align:left; padding:8px; border-bottom:1px solid #ddd;">Minuty</th>
          <th style="text-align:left; padding:8px; border-bottom:1px solid #ddd;">Řádek</th>
          <th style="text-align:left; padding:8px; border-bottom:1px solid #ddd;">NEXT</th>
          <th style="text-align:left; padding:8px; border-bottom:1px solid #ddd;">Barva</th>
          <th style="text-align:left; padding:8px; border-bottom:1px solid #ddd;">Další výměna za</th>
          <th style="text-align:left; padding:8px; border-bottom:1px solid #ddd;">NEXT_CHANGE_MIN</th>
        </tr>
      </thead>
      <tbody>
    """

    for row in rows:
        table_html += f"""
        <tr>
          <td style="padding:8px; border-bottom:1px solid #eee;">{html.escape(str(row["Úsek"]))}</td>
          <td style="padding:8px; border-bottom:1px solid #eee;">{html.escape(str(row["Interval"]))}</td>
          <td style="padding:8px; border-bottom:1px solid #eee;">{html.escape(str(row["Minuty"]))}</td>
          <td style="padding:8px; border-bottom:1px solid #eee;">{html.escape(str(row["Řádek"]))}</td>
          <td style="padding:8px; border-bottom:1px solid #eee;">{html.escape(str(row["NEXT"]))}</td>
          <td style="padding:8px; border-bottom:1px solid #eee;">{build_color_badge(str(row["Barva"]))}</td>
          <td style="padding:8px; border-bottom:1px solid #eee;">{html.escape(str(row["Další výměna za"]))}</td>
          <td style="padding:8px; border-bottom:1px solid #eee;">{html.escape(str(row["NEXT_CHANGE_MIN"]))}</td>
        </tr>
        """

    table_html += """
      </tbody>
    </table>
    """

    return table_html


def show_print_end_estimator(default_duration_min: Optional[int] = None):
    st.subheader("Odhad konce tisku")

    st.caption(
        "Čas se počítá podle časové zóny Europe/Prague. "
        "Zadej čas tisku podle OrcaSliceru a případný posun začátku kvůli nahřívání, "
        "heat soaku, bed meshi nebo ruční přípravě."
    )

    if default_duration_min is None:
        default_duration_min = 0

    default_hours, default_mins = divmod(int(default_duration_min), 60)

    col_a, col_b = st.columns(2)

    with col_a:
        duration_hours = st.number_input(
            "Čas tisku — hodiny",
            min_value=0,
            max_value=999,
            value=int(default_hours),
            step=1,
        )

    with col_b:
        duration_minutes = st.number_input(
            "Čas tisku — minuty",
            min_value=0,
            max_value=59,
            value=int(default_mins),
            step=1,
        )

    col_c, col_d = st.columns(2)

    with col_c:
        current_time = st.time_input(
            "Aktuální čas / čas výpočtu",
            value=datetime.now(PRAGUE_TZ).time().replace(second=0, microsecond=0),
        )

    with col_d:
        start_delay_minutes = st.number_input(
            "Posun začátku tisku v minutách",
            min_value=0,
            max_value=1440,
            value=0,
            step=1,
            help=(
                "Například 15 min pro heat soak, bed mesh, nahřátí "
                "nebo přípravu před reálným začátkem tisku."
            ),
        )

    duration_total = int(duration_hours) * 60 + int(duration_minutes)

    today_prague = datetime.now(PRAGUE_TZ).date()
    base_time = datetime.combine(today_prague, current_time, tzinfo=PRAGUE_TZ)

    real_start = base_time + timedelta(minutes=int(start_delay_minutes))
    estimated_end = real_start + timedelta(minutes=duration_total)

    if duration_total <= 0:
        st.info("Zadej čas tisku a zobrazí se odhad konce.")
        return

    col1, col2, col3 = st.columns(3)

    col1.metric("Reálný start", real_start.strftime("%H:%M"))
    col2.metric("Délka tisku", fmt_minutes(duration_total))
    col3.metric("Odhad konce", estimated_end.strftime("%H:%M"))

    if estimated_end.date() > real_start.date():
        st.warning(f"Tisk skončí další den v {estimated_end.strftime('%H:%M')}.")


st.set_page_config(
    page_title="M600 G-code intervaly",
    page_icon="🧵",
    layout="wide",
)

st.title("🧵 M600 G-code intervaly")
st.caption(
    "Nahraj G-code z OrcaSliceru. Appka spočítá intervaly mezi výměnami filamentu "
    "a umí doplnit NEXT_CHANGE_MIN do M600."
)

uploaded = st.file_uploader("Nahraj .gcode soubor", type=["gcode", "gco", "txt"])

lines = []
events = []
total_remaining: Optional[int] = None

if uploaded is not None:
    raw = uploaded.read()

    try:
        text = raw.decode("utf-8", errors="replace")
    except Exception:
        st.error("Soubor se nepodařilo přečíst jako text.")
        st.stop()

    try:
        lines, total_remaining, events = parse_gcode_text(text)
    except ValueError as error:
        st.error(str(error))
        st.stop()

    st.subheader("Souhrn")

    col1, col2, col3 = st.columns(3)

    col1.metric("Celkový odhad", fmt_minutes(total_remaining))
    col2.metric("Počet M600 výměn", len(events))
    col3.metric("Počet řádků", len(lines))

    if not events:
        st.warning("V souboru jsem nenašel žádné M600 výměny.")
    else:
        st.subheader("Intervaly výměn")

        rows = []

        for i, event in enumerate(events, start=1):
            label = "Start → 1. výměna" if i == 1 else f"{i - 1}. → {i}. výměna"

            rows.append(
                {
                    "Úsek": label,
                    "Interval": fmt_minutes(event["interval_from_prev"]),
                    "Minuty": event["interval_from_prev"],
                    "Řádek": event["line_number"],
                    "NEXT": event["next"],
                    "Barva": event["color"],
                    "Další výměna za": (
                        "poslední výměna"
                        if event["next_change_min"] < 0
                        else fmt_minutes(event["next_change_min"])
                    ),
                    "NEXT_CHANGE_MIN": event["next_change_min"],
                }
            )

        last = events[-1]

        rows.append(
            {
                "Úsek": f"{len(events)}. výměna → konec",
                "Interval": fmt_minutes(last["remaining"]),
                "Minuty": last["remaining"],
                "Řádek": "",
                "NEXT": "",
                "Barva": "",
                "Další výměna za": "",
                "NEXT_CHANGE_MIN": "",
            }
        )

        st.html(build_intervals_table_html(rows))

        st.subheader("M600 řádky")

        for i, event in enumerate(events, start=1):
            color_label = normalize_hex_color(event["color"]) or "bez barvy"

            with st.expander(f"{i}. výměna — řádek {event['line_number']} — {color_label}"):
                if event["color"]:
                    st.html(build_color_badge(event["color"]))

                st.code(event["line"], language="gcode")

                if event["next_change_min"] > 0:
                    st.write(f"Další výměna: **za {fmt_minutes(event['next_change_min'])}**")
                else:
                    st.write("Toto je poslední výměna filamentu.")

        st.subheader("Export upraveného G-code")

        modified = make_modified_gcode(lines, events)
        original_name = Path(uploaded.name)
        new_name = f"{original_name.stem}_nextchange{original_name.suffix or '.gcode'}"

        st.download_button(
            label="Stáhnout G-code s NEXT_CHANGE_MIN",
            data=modified.encode("utf-8"),
            file_name=new_name,
            mime="text/plain",
        )

        st.caption(
            "Poznámka: výpočet používá M73 R... hodnoty z OrcaSliceru, "
            "tedy odhad zbývajícího času ve chvíli M600."
        )
else:
    st.info("Nahraj G-code soubor a hned uvidíš intervaly výměn.")

st.divider()

show_print_end_estimator(default_duration_min=total_remaining)
