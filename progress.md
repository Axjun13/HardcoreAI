# HardcoreAI Implementation Progress

Last updated: 2026-07-18

## Completed

- Audited the earlier implementation of research items 3, 5, 6, and 7.
- Moved Embedded Configurator access into the View menu and made it hidden by default.
- Limited model selection to Google Gemini, DeepSeek, and Sarvam.
- Persisted the selected model and disabled providers whose API keys are missing.
- Added isolated research/ideation context windows with conversational follow-ups.
- Added per-context component selection and decision notes.
- Added final DeepSeek condensation with an explicit deterministic fallback when DeepSeek is unavailable.
- Unified research selections with visual-workbench selections for Phase 3, README generation, and Act mode.
- Added component deduplication, pin context, library documentation, datasheet, and purchase-search links.
- Added real Phase 3 PlatformIO dependency materialization into `.pio/libdeps`.
- Added an enriched Supabase component catalogue migration for ESP32 DevKit, SSD1306, DHT22, BME280, MPU6050, and hobby servos.
- Added regression tests for isolated research contexts and Research-to-Phase-3 component resolution.
- Added root `pytest.ini` so the documented test command can resolve both `backend.*` and backend-local imports.
- Registered released boards for STM32C0, STM32C5, STM32N6, STM32U0, STM32U3, STM32WB0, and STM32WBA using official ST product metadata.
- Removed STM32V8 from the operational HAL support set until ST publishes its board and full documentation; ST currently schedules public availability for Q3 2026.
- Added the exact 216-ball STM32F746NG TFBGA pinout from ST's official `STM32_open_pin_data` XML.
- Added embedding-model dependency injection to `RAGService`.
- Made RAG contract tests use LlamaIndex's deterministic local mock embedding, removing their first-run internet dependency without changing production FastEmbed behavior.
- Verified the complete repository:
  - Full backend suite: 291 tests passed, 0 failed, 0 errors.
  - Svelte check passed with 0 errors and 0 warnings.
  - Production frontend build passed.
  - Backend Python compilation passed.
  - `git diff --check` passed.

## Resolved Failure Pass

- All 17 pre-existing STM32 failures are resolved.
- All 3 network-related RAG setup errors are resolved.
- There are currently no failing automated tests.

## Remaining Product/Deployment Work

- Apply `supabase/migrations/20260718090000_enrich_research_component_catalogue.sql` to the target Supabase database.
- Configure DeepSeek and Sarvam keys if those providers should be enabled; currently only Gemini is configured.
- Perform an end-to-end manual run of Research → component selection → Condense → Phase 3 → README → Act mode against a real project.
- Add STM32V8 back to operational support after ST publishes a real board identifier, MCU order code, and full documentation.
- Review and commit the working-tree changes once the full verification pass is complete.
