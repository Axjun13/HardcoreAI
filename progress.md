# HardcoreAI Implementation Progress

Last updated: 2026-07-18

## Completed

- Audited the earlier implementation of research items 3, 5, 6, and 7.
- Moved Embedded Configurator access into the View menu and made it hidden by default.
- Limited model selection to Google Gemini, DeepSeek, and Sarvam.
- Persisted the selected model and disabled providers whose API keys are missing.
- Made the DeepSeek provider use the configured OpenRouter key and `deepseek/*` model route, while preserving optional direct DeepSeek API support.
- Added isolated research/ideation context windows with conversational follow-ups.
- Added per-context component selection and decision notes.
- Added final DeepSeek condensation with an explicit deterministic fallback when DeepSeek is unavailable.
- Unified research selections with visual-workbench selections for Phase 3, README generation, and Act mode.
- Added component deduplication, pin context, library documentation, datasheet, and purchase-search links.
- Added real Phase 3 PlatformIO dependency materialization into `.pio/libdeps`.
- Added an enriched Supabase component catalogue migration for ESP32 DevKit, SSD1306, DHT22, BME280, MPU6050, and hobby servos.
- Applied all pending idempotent migrations to the configured Supabase database and reconciled its migration history through `20260718090000`.
- Verified the deployed research catalogue contains all 6 enriched components and their 25 pin definitions.
- Added sourced product imagery, authoritative datasheets, and concrete purchase links for the initial 6 research components, with a resilient UI fallback for unavailable remote images.
- Applied and verified `20260718113000_add_component_product_metadata.sql` on the configured Supabase database.
- Completed a disposable live Research → selection → Phase 3 → Condense → README → Act-mode run using DeepSeek through OpenRouter:
  - All selected components and four inferred PlatformIO libraries reached the isolated Phase 3 context.
  - PlatformIO downloaded the dependencies into the project `.pio/libdeps` directory.
  - DeepSeek produced both the research condensation and the Act-mode response.
  - The generated README contained the board, selected components, libraries, and research handoff.
  - The disposable Supabase project and generated workspace were removed successfully.
- Added regression tests for isolated research contexts and Research-to-Phase-3 component resolution.
- Added root `pytest.ini` so the documented test command can resolve both `backend.*` and backend-local imports.
- Registered released boards for STM32C0, STM32C5, STM32N6, STM32U0, STM32U3, STM32WB0, and STM32WBA using official ST product metadata.
- Removed STM32V8 from the operational HAL support set until ST publishes its board and full documentation; ST currently schedules public availability for Q3 2026.
- Added the exact 216-ball STM32F746NG TFBGA pinout from ST's official `STM32_open_pin_data` XML.
- Added embedding-model dependency injection to `RAGService`.
- Made RAG contract tests use LlamaIndex's deterministic local mock embedding, removing their first-run internet dependency without changing production FastEmbed behavior.
- Verified the complete repository:
  - Full backend suite: 294 tests passed, 0 failed, 0 errors.
  - Svelte check passed with 0 errors and 0 warnings.
  - Production frontend build passed.
  - Backend Python compilation passed.
  - `git diff --check` passed.

## Resolved Failure Pass

- All 17 pre-existing STM32 failures are resolved.
- All 3 network-related RAG setup errors are resolved.
- There are currently no failing automated tests.

## Remaining Product/Deployment Work

- Sarvam configuration is intentionally deferred to the interns and is not required for the DeepSeek/OpenRouter workflow.
- Add STM32V8 back to operational support after ST publishes a real board identifier, MCU order code, and full documentation.
- Review and commit the completed implementation and verification changes.
