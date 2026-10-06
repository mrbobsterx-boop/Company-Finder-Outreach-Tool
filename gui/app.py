"""Local button-driven UI over the same core packages the CLI uses.

Run with: streamlit run gui/app.py
Opens in your browser at http://localhost:8501 — everything happens on
your own machine, nothing is deployed anywhere. This file only wires
Streamlit widgets to the existing discovery/enrichment/storage/compliance/
mailer modules; it holds no business logic of its own (that stays in one
place, shared with cli/main.py).
"""
from __future__ import annotations

import sys
from pathlib import Path

# Streamlit only adds this script's own directory (gui/) to sys.path, not
# the repository root — unlike `python -m cli`, which the shell's cwd
# already puts there. Without this, `import compliance`/`storage`/... fails
# with ModuleNotFoundError regardless of which directory streamlit is
# launched from.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st
import yaml

from compliance import RecipientCandidate, filter_recipients
from config import load_config
from discovery import OSMDiscoveryProvider
from enrichment.scraper import CompanyScraper
from mailer import SMTPMailProvider
from mailer.templating import build_unsubscribe_url, render_template
from storage import Company, Contact, OutreachLogEntry, Repository, init_db

st.set_page_config(page_title="Company Finder & Outreach", page_icon="\U0001F4C7", layout="wide")


@st.cache_resource
def get_config() -> dict:
    return load_config()


@st.cache_resource
def get_repository(db_path: str) -> Repository:
    conn = init_db(db_path)
    return Repository(conn)


def rows_to_df(rows) -> pd.DataFrame:
    return pd.DataFrame([dict(row) for row in rows])


config = get_config()
repo = get_repository(config["database"]["path"])

st.sidebar.title("Company Finder")
page = st.sidebar.radio(
    "Раздел",
    [
        "🔍 Поиск компаний",
        "📇 Сбор контактов",
        "📤 Экспорт",
        "✉️ Рассылка",
        "🗄️ База данных",
        "⚙️ Настройки",
    ],
)
st.sidebar.caption(f"База: `{config['database']['path']}`")
st.sidebar.caption(f"Компаний в базе: {repo.count_companies()}")


# --------------------------------------------------------------------- discover
if page == "🔍 Поиск компаний":
    st.header("Поиск компаний через OpenStreetMap")
    st.caption("Бесплатно, без API-ключа. Не запускайте слишком часто подряд — есть fair-use лимиты.")

    with st.form("discover_form"):
        col1, col2 = st.columns(2)
        country = col1.text_input("Страна (код, напр. UA)", "UA")
        region = col2.text_input("Регион (необязательно)", "")
        city = col1.text_input("Город (необязательно)", "Poltava")
        category = col2.text_input("Категория бизнеса (напр. dentist, webdev, restaurant)", "dentist")
        submitted = st.form_submit_button("Найти компании", type="primary")

    if submitted:
        if not country or not category:
            st.error("Страна и категория обязательны.")
        else:
            with st.spinner("Запрашиваю Photon и Overpass..."):
                provider = OSMDiscoveryProvider(
                    overpass_fallback_urls=config["discovery"]["overpass_urls"],
                    geocoder_base_url=config["discovery"]["geocoder_base_url"],
                    user_agent=config["discovery"]["user_agent"],
                    request_delay_seconds=config["discovery"]["request_delay_seconds"],
                    bbox_radius_km=config["discovery"]["bbox_radius_km"],
                )
                companies = provider.search(
                    country=country, region=region or None, city=city or None, category=category
                )
                for company in companies:
                    company.country = country
                for company in companies:
                    repo.upsert_company(company)

            if not companies:
                st.warning("Ничего не найдено — попробуйте другой город/категорию.")
            else:
                st.success(f"Найдено и сохранено {len(companies)} компаний.")
                st.dataframe(
                    pd.DataFrame([c.__dict__ for c in companies]),
                    use_container_width=True,
                )


# ----------------------------------------------------------------------- enrich
elif page == "📇 Сбор контактов":
    st.header("Сбор email/телефона с сайтов компаний")
    st.caption("Идёт по сайту компании, ищет страницы контактов/о нас/impressum, вытаскивает email и телефон.")

    col1, col2 = st.columns(2)
    batch = col1.number_input("Сколько компаний обработать", min_value=1, max_value=2000, value=50)
    force = col2.checkbox("Пересканировать компании, где контакты уже есть")

    if st.button("Запустить сбор контактов", type="primary"):
        scraper = CompanyScraper(
            contact_page_keywords=config["enrichment"]["contact_page_keywords"],
            user_agent=config["enrichment"]["user_agent"],
            cache_dir=config["enrichment"]["cache_dir"],
            domain_delay_seconds=config["enrichment"]["domain_delay_seconds"],
            min_delay_seconds=config["enrichment"]["min_delay_seconds"],
            max_delay_seconds=config["enrichment"]["max_delay_seconds"],
            request_timeout_seconds=config["enrichment"]["request_timeout_seconds"],
            ai_fallback_config=config["enrichment"]["ai_fallback"],
            repository=repo,
        )

        companies = repo.list_companies(only_with_website=True, only_without_contacts=not force)
        batch_rows = companies[:batch]

        if not batch_rows:
            st.info("Нет компаний для обработки (у всех либо нет сайта, либо контакты уже есть).")
        else:
            progress = st.progress(0.0, text="Обрабатываю...")
            status_area = st.empty()
            found = 0
            results = []

            for i, row in enumerate(batch_rows):
                status_area.text(f"{row['name']} — {row['website']}")
                result = scraper.scrape_company(row["website"], default_region=row["country"])

                if result.emails or result.phones:
                    found += 1
                    for email in result.emails or [None]:
                        repo.add_contact(
                            Contact(
                                company_id=row["id"],
                                email=email,
                                phone=result.phones[0] if result.phones else None,
                                source_page=result.source_page,
                                confidence=0.4 if result.used_ai_fallback else 0.9,
                            )
                        )

                results.append(
                    {
                        "company": row["name"],
                        "website": row["website"],
                        "emails": ", ".join(result.emails),
                        "phones": ", ".join(result.phones),
                        "источник": result.source_page or "",
                    }
                )
                progress.progress((i + 1) / len(batch_rows))

            status_area.empty()
            st.success(f"Обработано {len(batch_rows)} компаний, контакты найдены у {found}.")
            st.dataframe(pd.DataFrame(results), use_container_width=True)


# ----------------------------------------------------------------------- export
elif page == "📤 Экспорт":
    st.header("Экспорт в CSV")

    only_verified = st.checkbox("Только компании с найденным email", value=True)
    rows = repo.list_verified_contacts() if only_verified else repo.list_companies()

    if not rows:
        st.info("Нет данных для экспорта.")
    else:
        df = rows_to_df(rows)
        st.dataframe(df, use_container_width=True)
        st.download_button(
            "⬇️ Скачать CSV",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name="export.csv",
            mime="text/csv",
            type="primary",
        )


# ------------------------------------------------------------------------- send
elif page == "✉️ Рассылка":
    st.header("Email-рассылка")

    with st.form("send_form"):
        template = st.text_input("Шаблон", "offer_v1.html")
        subject = st.text_input("Тема письма", "A quick idea for your business")
        offer_text = st.text_area("Текст предложения", "We help businesses like yours grow online.")
        col1, col2 = st.columns(2)
        limit = col1.number_input("Лимит получателей", min_value=1, max_value=1000, value=50)
        force = col2.checkbox("Игнорировать лимит частоты повторной отправки (--force)")
        allow_strict = st.checkbox(
            "Разрешить страны со строгими правилами cold-email (DE/IT/AT/FR и др.)"
        )
        preview_clicked = st.form_submit_button("Показать, кому уйдёт (dry-run)", type="primary")

    if preview_clicked:
        candidates = [
            RecipientCandidate(
                company_id=row["id"], company_name=row["name"],
                country=row["country"], email=row["contact_email"],
            )
            for row in repo.list_verified_contacts()
        ]
        decisions = filter_recipients(
            candidates, repo, config["compliance"], force=force, allow_strict_countries=allow_strict,
        )
        st.session_state["send_decisions"] = decisions
        st.session_state["send_params"] = dict(
            template=template, subject=subject, offer_text=offer_text, limit=int(limit),
        )

    decisions = st.session_state.get("send_decisions")
    if decisions is not None:
        params = st.session_state["send_params"]
        allowed = [d for d in decisions if d.allowed][: params["limit"]]
        skipped = [d for d in decisions if not d.allowed]

        st.subheader(f"Получат письмо: {len(allowed)}")
        if allowed:
            st.dataframe(
                pd.DataFrame(
                    [{"компания": d.candidate.company_name, "email": d.candidate.email} for d in allowed]
                ),
                use_container_width=True,
            )

        st.subheader(f"Пропущено фильтрами комплаенса: {len(skipped)}")
        if skipped:
            reason_counts: dict[str, int] = {}
            for d in skipped:
                for reason in d.reasons:
                    reason_counts[reason] = reason_counts.get(reason, 0) + 1
            st.dataframe(
                pd.DataFrame(
                    [{"причина": reason, "кол-во": count} for reason, count in reason_counts.items()]
                ),
                use_container_width=True,
            )

        if allowed:
            st.divider()
            st.warning("⚠️ Реальная отправка — необратимое действие. Проверьте список выше.")
            confirm = st.checkbox("Я подтверждаю, что хочу отправить письма по-настоящему", key="confirm_send")
            if st.button("🚀 Отправить по-настоящему", disabled=not confirm, type="primary"):
                mail_provider = SMTPMailProvider(
                    host=config["mailer"]["smtp_host"],
                    port=config["mailer"]["smtp_port"],
                    username=config["mailer"]["smtp_username"],
                    password=config["mailer"]["smtp_password"],
                    from_email=config["mailer"]["from_email"],
                    from_name=config["mailer"]["from_name"],
                    throttle_seconds=config["mailer"]["throttle_seconds"],
                )
                progress = st.progress(0.0, text="Отправляю...")
                sent_count = 0
                for i, decision in enumerate(allowed):
                    candidate = decision.candidate
                    unsubscribe_url = build_unsubscribe_url(
                        config["mailer"]["unsubscribe_base_url"], candidate.email
                    )
                    html_body = render_template(
                        config["mailer"]["templates_dir"],
                        params["template"],
                        {
                            "company_name": candidate.company_name,
                            "city": "",
                            "offer_text": params["offer_text"],
                            "sender_name": config["mailer"]["from_name"],
                            "unsubscribe_url": unsubscribe_url,
                        },
                    )
                    result = mail_provider.send(candidate.email, params["subject"], html_body)
                    repo.log_outreach(
                        OutreachLogEntry(
                            company_id=candidate.company_id, email=candidate.email, status=result.status,
                        )
                    )
                    if result.status == "sent":
                        sent_count += 1
                    progress.progress((i + 1) / len(allowed))

                st.success(f"Отправлено {sent_count} из {len(allowed)} писем.")
                del st.session_state["send_decisions"]


# -------------------------------------------------------------------------- db
elif page == "🗄️ База данных":
    st.header("Содержимое базы данных")
    tab_companies, tab_contacts, tab_outreach, tab_unsub = st.tabs(
        ["Компании", "Контакты", "История рассылок", "Отписавшиеся"]
    )
    with tab_companies:
        st.dataframe(rows_to_df(repo.list_companies()), use_container_width=True)
    with tab_contacts:
        st.dataframe(rows_to_df(repo.list_all_contacts()), use_container_width=True)
    with tab_outreach:
        st.dataframe(rows_to_df(repo.list_outreach_log()), use_container_width=True)
    with tab_unsub:
        st.dataframe(rows_to_df(repo.list_unsubscribed()), use_container_width=True)


# -------------------------------------------------------------------- settings
elif page == "⚙️ Настройки":
    st.header("Настройки (config.yaml)")
    cfg_path = Path("config.yaml")
    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
    raw = raw or {}
    mailer_raw = raw.get("mailer", {})

    st.caption(
        "Здесь редактируются только настройки почты. Изменения сохраняются в config.yaml "
        "и применяются после перезапуска (сообщение об этом появится ниже)."
    )

    with st.form("settings_form"):
        smtp_host = st.text_input("SMTP host", mailer_raw.get("smtp_host", config["mailer"]["smtp_host"]))
        smtp_port = st.number_input(
            "SMTP port", value=int(mailer_raw.get("smtp_port", config["mailer"]["smtp_port"]))
        )
        smtp_username = st.text_input("SMTP username", mailer_raw.get("smtp_username", ""))
        smtp_password = st.text_input(
            "SMTP password", mailer_raw.get("smtp_password", ""), type="password"
        )
        from_email = st.text_input("Email отправителя", mailer_raw.get("from_email", config["mailer"]["from_email"]))
        from_name = st.text_input("Имя отправителя", mailer_raw.get("from_name", config["mailer"]["from_name"]))
        unsubscribe_base_url = st.text_input(
            "URL страницы отписки",
            mailer_raw.get("unsubscribe_base_url", config["mailer"]["unsubscribe_base_url"]),
        )
        save = st.form_submit_button("Сохранить настройки", type="primary")

    if save:
        raw.setdefault("mailer", {}).update(
            {
                "smtp_host": smtp_host,
                "smtp_port": int(smtp_port),
                "smtp_username": smtp_username,
                "smtp_password": smtp_password,
                "from_email": from_email,
                "from_name": from_name,
                "unsubscribe_base_url": unsubscribe_base_url,
            }
        )
        cfg_path.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8")
        get_config.clear()
        st.success("Сохранено. Обновите страницу (F5), чтобы применить новые настройки.")
