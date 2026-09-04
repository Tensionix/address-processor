# Карта файлов проекта

[English](PROJECT_FILES_GUIDE_EN.md) · [Справочник](../REFERENCE_RU.md) · [Установка](../INSTALL_RU.md)

Где что лежит. Документ для того, кто будет сопровождать проект: пользователю он
не нужен.

Рабочие папки (`input`, `output`, `logs`, `report`, `release`, `workspace`,
`runtime`, `wheelhouse`) описаны по роли, а не пофайлово — их содержимое
порождается прогонами и пересобирается.

---

## Корень

| Файл | Что это |
| --- | --- |
| `Start.exe` | Скомпилированный запуск окна |
| `launcher_gui.cmd` | Запуск окна |
| `launcher_project.cmd` | Меню проекта, английское |
| `launcher_project_ru.cmd` | Меню проекта, русское |
| `launcher_tools.cmd` | Служебное меню: doctor, лицензии, релиз |
| `builder_main.cmd` | Сборка portable-окружения |
| `cleanup_project.cmd` | Очистка наработанных артефактов |
| `pytest.ini` | Настройки тестов |
| `release_manifest.json` | Манифест последней сборки релиза |
| `README.md` | Публичное описание проекта |

CMD-файлы должны оставаться UTF-8 без BOM с переносами CRLF. После правки —
`install\Check-CmdEncoding.cmd`.

---

## `config` — настройки

| Файл | Что это |
| --- | --- |
| `project.yaml` | Настройки движка: город, эталонная колонка, целевые колонки, связанные колонки, ограничения безопасности |
| `gui_settings.yaml` | Язык, тема, поведение окна |
| `tool_manifest.yaml` | Описание всех команд и полей окна; из него строится интерфейс |
| `version.json` | Версия и язык корневого README |
| `ui_colors.yaml` | Цвета интерфейса |
| `path_history.json` | История и закрепления путей источника и назначения |
| `oktmo_current_keys.txt` | Текущие ключи поиска ОКТМО |
| `oktmo_region_pins.json` | Закреплённые регионы |
| `oktmo_municipality_pins.json` | Закреплённые муниципалитеты |
| `oktmo_pins_bundle.json` | Общий набор пинов |

---

## `system_core` — код

### Верхний уровень

| Файл | Что делает |
| --- | --- |
| `Ultimate_GT_Aligner.py` | Движок сопоставления: разбор адреса, проходы, перенос связанных колонок |
| `safe_table_join.py` | Сравнение двух книг и перенос колонок через Excel |
| `excel_layout.py` | Оформление книг результата: ширина колонок, перенос текста, заливка |
| `remove_empty_rows.py` | Удаление полностью пустых строк |
| `Parser_Diagnostic.py` | Диагностика разбора адреса |
| `inspect_md_tables.py` | Разбор таблиц в Markdown |
| `doctor.py` | Проверка окружения и импортов |
| `main.py` | Прямой запуск сопоставления без окна |
| `fzf.exe` | Меню для CMD-launcher-ов |

### `address_engine` — адресный движок

| Файл | Что делает |
| --- | --- |
| `audion_address_core.py` | Разбор адреса на составляющие, распознавание адресоподобного текста |
| `address_slots.py` | Слоты: определение, заполнение, сборка адресной строки |
| `slot_fill.py` | Заполнение слотов из свидетельств |
| `models.py` | Структуры данных: наблюдение, составляющие адреса, отпечаток, кластер |
| `source_intake.py` | Чтение источников всех поддерживаемых форматов |
| `source_table_assembly.py` | Сбор адресов из источников в книгу |
| `source_cleanup.py` | Отсев временных файлов Office |
| `reference_builder.py` | Построение эталонного справочника, определение слотов и колонок |
| `reference_processor.py` | Сортировка и разложение справочника по слотам |
| `oktmo_lookup.py` | Индекс ОКТМО, дисковый кэш, поиск региона, МО и населённого пункта |
| `oktmo_user_keys.py` | Файл ключей проекта и пины |
| `rosstat_update.py` | Скачивание и обновление реестра Росстата |
| `region_reference.py` | Справочник регионов |
| `russian_morphology.py` | Падежные формы названий |
| `universal_address.py` | Общий нормализатор адреса |
| `normalizer_runtime.py` | Настройка нормализатора под прогон |
| `address_diagnostics.py` | Диагностические выборки |
| `legacy_office_converter.py` | Конвертация DOC/XLS |

### `services` — сервисный слой

`address_aligner_service.py` — единственный файл. Каждая команда окна ссылается
на функцию отсюда: сервис принимает параметры, вызывает движок, пишет журнал,
отчёт и список артефактов.

### `ui_nicegui` — окно

| Файл | Что делает |
| --- | --- |
| `window.py` | Обёртка окна: порт, иконка, движок WebView2 |
| `app.py` | Сам интерфейс: команды, поля, журнал, панели ОКТМО |
| `workbench.py` | Источник и назначение, история путей, закрепления |
| `i18n.py` | Переключение языка |
| `tokens.css`, `base.css`, `theme.css` | Оформление |

### `core` — ядро

| Файл | Что делает |
| --- | --- |
| `jobs.py` | Запуск операций, отмена, прогресс |
| `manifest.py` | Разбор `tool_manifest.yaml` |
| `paths.py` | Управляемые папки проекта |
| `config.py` | Чтение настроек |
| `ui_settings.py` | Настройки окна |
| `ansi_terminal.py` | Терминальный вывод в журнал |
| `cmd_encoding.py` | Проверка кодировок CMD |
| `output_decode.py` | Декодирование вывода подпроцессов |
| `logging_utils.py` | Журналирование |

### Прочее

| Путь | Что это |
| --- | --- |
| `license/` | Сбор, дедупликация и очистка лицензий сторонних компонентов |
| `icons/` | Иконки окна |
| `start_launcher/` | Исходник `Start.exe` |
| `powershell/` | Вспомогательные скрипты |

---

## `install` — установка и сборка

| Файл | Что делает |
| --- | --- |
| `Build_Portable_Env.cmd` / `.ps1` | Сборка portable-окружения |
| `install_portable_offline.cmd` | Установка из локального `wheelhouse` |
| `verify_portable_env.cmd` | Проверка собранного окружения |
| `init_folders.cmd` | Создание рабочих папок |
| `Check-CmdEncoding.cmd`, `Repair-CmdEncoding.ps1` | Проверка и починка кодировок CMD |
| `Clean-Install-Cache.cmd` / `.ps1` | Очистка кэша сборки |
| `Update-Requirements-Lock.cmd` | Обновление lock-файла зависимостей |
| `make_release_archive.cmd` | Сборка релизного архива |
| `Build-StartLauncher.cmd` / `.ps1` | Сборка `Start.exe` |
| `launcher-tools-update_fzf.cmd` | Обновление `fzf.exe` |
| `requirements_full.in` | Список зависимостей |
| `README_INSTALL.md` | Заметки по установке |

---

## `data` — данные

| Путь | Что это |
| --- | --- |
| `regions_reference.yaml` | Справочник регионов |
| `rosstat/data-*.csv` | Реестр ОКТМО, скачивается кнопкой в окне |
| `rosstat/oktmo_lookup_cache.json` | Разобранный индекс ОКТМО |

---

## `docs` — документация

| Файл | Что это |
| --- | --- |
| `README_RU.md`, `README_EN.md` | Описание проекта, точка входа |
| `USER_GUIDE_RU.md`, `USER_GUIDE_EN.md` | Руководство пользователя |
| `OKTMO_RU.md`, `OKTMO_EN.md` | Реестр ОКТМО, ключи и пины |
| `REFERENCE_RU.md`, `REFERENCE_EN.md` | Технический справочник |
| `INSTALL_RU.md`, `INSTALL_EN.md` | Установка и запуск |
| `tools/PROJECT_FILES_GUIDE_*.md` | Этот документ |
| `PDF/` | Отрендеренные PDF всех документов в двух темах |

PDF собираются отдельным инструментом из всех `.md` в `docs`, включая вложенные
папки. Структура папок сохраняется.

---

## `tests` — тесты

| Файл | Что проверяет |
| --- | --- |
| `test_address_aligner_regression.py` | Проходы сопоставления |
| `test_safe_table_join.py` | Перенос колонок по адресу |
| `test_excel_layout.py` | Оформление книг результата |
| `test_gui_render.py` | Отрисовка окна |
| `test_workbench_route_regression.py` | Источник и назначение |
| `test_ansi_terminal.py` | Терминальный вывод |

Окно тестируется headless-фикстурой NiceGUI с разбором страницы через
BeautifulSoup; selenium сознательно не используется.

---

## `licenses` — лицензии

Тексты лицензий сторонних компонентов, `THIRD_PARTY_NOTICES.txt`,
`COMPONENTS.json`, отчёт сканирования и манифест пакета. Собираются
инструментами из `system_core/license/`.
