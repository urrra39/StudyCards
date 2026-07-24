# Key decisions — Phase 6 (Streamlit demo)

## Why one page, not a multipage app
Upload → extract → review is a single loop. Multipage navigation would break
the "rate and see due date update live" flow across reruns. Session state
holds the active card; the DB is the source of truth for everything else.

## Why `CardRepository` is cached in `st.session_state`
Avoids re-running schema init on every widget click, while still opening a
fresh SQLite connection per operation (see Phase 4). The repo object is
cheap; the schema check is the part worth caching.

## Why model discovery runs on every sidebar render
Keys change as the user types. Caching by key hash is possible but races
with the "I just pasted a key" moment. Discovery is a single HTTP call with
hard fallbacks — fine to repeat. The caption tells the user whether they
are seeing live or fallback models.

## Why headless boot is a real HTTP check, not just an import
Import-only tests miss Streamlit config errors, missing `st.set_page_config`
ordering issues, and port binding failures. We spawn `streamlit run
--server.headless`, wait for HTTP 200, then terminate.
