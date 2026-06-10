"""Lightweight UI translations (English / Russian / Azerbaijani).

The English string is used as the key, so wrapping code reads naturally:
``t("Start Recovery")``. ``set_language()`` switches the active language and the
app rebuilds its screens so every window updates.
"""
from __future__ import annotations

LANGUAGES = [("English", "en"), ("Русский", "ru"), ("Azərbaycan", "az")]
_NAME_TO_CODE = {name: code for name, code in LANGUAGES}
_CODE_TO_NAME = {code: name for name, code in LANGUAGES}

_lang = "en"

# English -> {ru, az}. Missing entries fall back to the English key.
_TR: dict[str, dict[str, str]] = {
    # -- chrome / app ---------------------------------------------------
    "read-only - offline": {"ru": "только чтение - офлайн", "az": "yalnız oxuma - offline"},
    "Privacy & Limits": {"ru": "Конфиденциальность", "az": "Məxfilik və limitlər"},
    "Language": {"ru": "Язык", "az": "Dil"},
    "Privacy & Limitations": {"ru": "Конфиденциальность и ограничения",
                              "az": "Məxfilik və məhdudiyyətlər"},
    "Quit": {"ru": "Выход", "az": "Çıxış"},
    "A scan is running. Stop it and quit?":
        {"ru": "Идёт сканирование. Остановить и выйти?",
         "az": "Skan davam edir. Dayandırıb çıxılsın?"},
    "Scan error": {"ru": "Ошибка сканирования", "az": "Skan xətası"},
    # -- welcome --------------------------------------------------------
    "Professional data recovery for HDD, SSD, USB drives, memory cards and disk images.":
        {"ru": "Профессиональное восстановление данных для HDD, SSD, USB, карт памяти и образов дисков.",
         "az": "HDD, SSD, USB, yaddaş kartları və disk imicləri üçün peşəkar məlumat bərpası."},
    "Get started": {"ru": "Начало работы", "az": "Başlayaq"},
    "Choose a physical disk to scan, or open an existing disk image file.":
        {"ru": "Выберите физический диск для сканирования или откройте файл образа диска.",
         "az": "Skan üçün fiziki disk seçin və ya mövcud disk imici faylını açın."},
    "Start Recovery": {"ru": "Начать восстановление", "az": "Bərpanı başlat"},
    "Open Disk Image...": {"ru": "Открыть образ диска...", "az": "Disk imicini aç..."},
    "Deep Scan + Carving": {"ru": "Глубокое сканирование + Carving",
                            "az": "Dərin skan + Carving"},
    "Recover JPG, PNG, PDF, Office, ZIP, MP4 and more by signature.":
        {"ru": "Восстановление JPG, PNG, PDF, Office, ZIP, MP4 и других по сигнатуре.",
         "az": "JPG, PNG, PDF, Office, ZIP, MP4 və digərlərini imzaya görə bərpa edir."},
    "Safe by design": {"ru": "Безопасно по умолчанию", "az": "Dizayna görə təhlükəsiz"},
    "Sources are opened read-only. Nothing is written back to them.":
        {"ru": "Источники открываются только для чтения. На них ничего не записывается.",
         "az": "Mənbələr yalnız oxuma üçün açılır. Onlara heç nə yazılmır."},
    "Preview before recovery": {"ru": "Предпросмотр перед восстановлением",
                                "az": "Bərpadan əvvəl önizləmə"},
    "Inspect images and text before restoring to a safe folder.":
        {"ru": "Просмотр изображений и текста перед сохранением в безопасную папку.",
         "az": "Təhlükəsiz qovluğa bərpadan əvvəl şəkil və mətnə baxın."},
    "Safety: Never recover files back onto the same disk you are scanning. For failing drives, create a disk image first. Recovery is never guaranteed.":
        {"ru": "Безопасность: Никогда не восстанавливайте файлы на тот же диск, который сканируете. Для неисправных дисков сначала создайте образ. Восстановление не гарантируется.",
         "az": "Təhlükəsizlik: Faylları skan etdiyiniz diskə bərpa etməyin. Nasaz disklər üçün əvvəlcə imic yaradın. Bərpa heç vaxt zəmanətli deyil."},
    "Open disk image": {"ru": "Открыть образ диска", "az": "Disk imicini aç"},
    # -- device select --------------------------------------------------
    "Select a device": {"ru": "Выберите устройство", "az": "Cihaz seçin"},
    "Choose a disk or partition to scan. All access is read-only.":
        {"ru": "Выберите диск или раздел для сканирования. Доступ только для чтения.",
         "az": "Skan üçün disk və ya bölmə seçin. Bütün giriş yalnız oxuma."},
    "Refresh": {"ru": "Обновить", "az": "Yenilə"},
    "Filter by name, type or filesystem...":
        {"ru": "Фильтр по имени, типу или файловой системе...",
         "az": "Ad, tip və ya fayl sisteminə görə süzgəc..."},
    "Scanning for devices...": {"ru": "Поиск устройств...", "az": "Cihazlar axtarılır..."},
    "{n} device(s) detected.": {"ru": "Обнаружено устройств: {n}.", "az": "{n} cihaz tapıldı."},
    "No devices found. Run as Administrator to access physical disks, or use 'Open Disk Image' from the welcome screen.":
        {"ru": "Устройства не найдены. Запустите от имени администратора или используйте 'Открыть образ диска'.",
         "az": "Cihaz tapılmadı. Administrator kimi işə salın və ya 'Disk imicini aç' istifadə edin."},
    "Details": {"ru": "Подробности", "az": "Detallar"},
    "Choose what to scan": {"ru": "Выберите, что сканировать", "az": "Nəyi skan edəcəyinizi seçin"},
    "Disks": {"ru": "Диски", "az": "Disklər"},
    "Health:": {"ru": "Здоровье:", "az": "Sağlamlıq:"},
    "Entire disk  ({size})": {"ru": "Весь диск  ({size})", "az": "Bütün disk  ({size})"},
    "Raw scan across the whole device - best for lost partitions":
        {"ru": "Сканирование всего устройства - лучше для потерянных разделов",
         "az": "Bütün cihazın skanı - itmiş bölmələr üçün ən yaxşısı"},
    "No label": {"ru": "Без метки", "az": "Adsız"},
    "Unknown FS": {"ru": "Неизв. ФС", "az": "Naməlum FS"},
    "{size} free": {"ru": "{size} свободно", "az": "{size} boş"},
    "SSD detected: if TRIM has erased deleted data, recovery may be impossible.":
        {"ru": "Обнаружен SSD: если TRIM стёр данные, восстановление может быть невозможно.",
         "az": "SSD aşkarlandı: TRIM silinmiş datanı təmizləyibsə, bərpa mümkün olmaya bilər."},
    "Back": {"ru": "Назад", "az": "Geri"},
    "Continue": {"ru": "Продолжить", "az": "Davam et"},
    # -- scan mode ------------------------------------------------------
    "Choose a scan mode": {"ru": "Выберите режим сканирования", "az": "Skan rejimini seçin"},
    "Each mode reads the source only - it never writes to it.":
        {"ru": "Каждый режим только читает источник и никогда в него не пишет.",
         "az": "Hər rejim mənbəni yalnız oxuyur - heç vaxt ona yazmır."},
    "Quick Scan": {"ru": "Быстрое сканирование", "az": "Sürətli skan"},
    "Fast signature pass over the first region. Best for recently deleted files.":
        {"ru": "Быстрый проход по сигнатурам первой области. Для недавно удалённых файлов.",
         "az": "İlk bölgədə sürətli imza keçidi. Yaxınlarda silinmiş fayllar üçün."},
    "Deep Scan": {"ru": "Глубокое сканирование", "az": "Dərin skan"},
    "Full read-only scan with raw file carving. Best for formatted or corrupted media.":
        {"ru": "Полное сканирование с carving. Для отформатированных или повреждённых носителей.",
         "az": "Carving ilə tam skan. Formatlanmış və ya zədələnmiş daşıyıcılar üçün."},
    "Lost Partition Scan": {"ru": "Поиск потерянных разделов", "az": "İtmiş bölmə skanı"},
    "Probe the whole device for boot sectors / partitions, then carve. Use when partitions are gone.":
        {"ru": "Поиск загрузочных секторов / разделов по всему устройству. Когда разделы потеряны.",
         "az": "Bütün cihazda boot sektor / bölmə axtarışı, sonra carving. Bölmələr itəndə."},
    "Disk Image Scan": {"ru": "Сканирование образа диска", "az": "Disk imici skanı"},
    "Carve a disk image file (.img/.dd/.raw/.iso) instead of a physical disk.":
        {"ru": "Carving файла образа диска (.img/.dd/.raw/.iso) вместо физического диска.",
         "az": "Fiziki disk yerinə disk imici faylının (.img/.dd/.raw/.iso) carving-i."},
    "Source: {name}  ({type})": {"ru": "Источник: {name}  ({type})", "az": "Mənbə: {name}  ({type})"},
    "Start Scan": {"ru": "Начать скан", "az": "Skanı başlat"},
    "Disk Image Scan expects an image file. Use 'Open Disk Image' from the welcome screen.":
        {"ru": "Для этого режима нужен файл образа. Используйте 'Открыть образ диска'.",
         "az": "Bu rejim imic faylı tələb edir. 'Disk imicini aç' istifadə edin."},
    "This is an SSD. If TRIM cleared the data, recovery may be impossible.":
        {"ru": "Это SSD. Если TRIM очистил данные, восстановление может быть невозможно.",
         "az": "Bu SSD-dir. TRIM datanı təmizləyibsə, bərpa mümkün olmaya bilər."},
    "Tip: For failing drives, image the disk first, then scan the image.":
        {"ru": "Совет: для неисправных дисков сначала создайте образ, затем сканируйте его.",
         "az": "Məsləhət: nasaz disklər üçün əvvəlcə imic yaradın, sonra onu skan edin."},
    # -- scan progress --------------------------------------------------
    "Scanning...": {"ru": "Сканирование...", "az": "Skan edilir..."},
    "Scanned": {"ru": "Просканировано", "az": "Skan edilib"},
    "Total": {"ru": "Всего", "az": "Cəmi"},
    "Files found": {"ru": "Найдено файлов", "az": "Tapılan fayllar"},
    "Est. remaining": {"ru": "Осталось (оц.)", "az": "Təxmini qalıq"},
    "Detected types: -": {"ru": "Обнаруженные типы: -", "az": "Tapılan tiplər: -"},
    "Detected types: ": {"ru": "Обнаруженные типы: ", "az": "Tapılan tiplər: "},
    "Activity log": {"ru": "Журнал действий", "az": "Fəaliyyət jurnalı"},
    "Pause": {"ru": "Пауза", "az": "Dayandır"},
    "Resume": {"ru": "Продолжить", "az": "Davam et"},
    "Stop": {"ru": "Стоп", "az": "Dayan"},
    "View Results": {"ru": "Показать результаты", "az": "Nəticələrə bax"},
    # -- results --------------------------------------------------------
    "Results": {"ru": "Результаты", "az": "Nəticələr"},
    "Results - {n} file(s) found": {"ru": "Результаты - найдено файлов: {n}",
                                    "az": "Nəticələr - {n} fayl tapıldı"},
    "Search filename...": {"ru": "Поиск по имени...", "az": "Fayl adı ilə axtar..."},
    "All types": {"ru": "Все типы", "az": "Bütün tiplər"},
    "All": {"ru": "Все", "az": "Hamısı"},
    "All categories": {"ru": "Все категории", "az": "Bütün kateqoriyalar"},
    "Open: all": {"ru": "Открытие: все", "az": "Açılma: hamısı"},
    "Openable": {"ru": "Открываемые", "az": "Açıla bilən"},
    "Won't open": {"ru": "Не открывается", "az": "Açılmır"},
    "Unverified": {"ru": "Не проверено", "az": "Yoxlanmayıb"},
    "Select all": {"ru": "Выбрать все", "az": "Hamısını seç"},
    "Clear": {"ru": "Очистить", "az": "Təmizlə"},
    "Re-check openability": {"ru": "Перепроверить открытие", "az": "Açılmanı yenidən yoxla"},
    "Checking {d}/{t}...": {"ru": "Проверка {d}/{t}...", "az": "Yoxlanılır {d}/{t}..."},
    "File name": {"ru": "Имя файла", "az": "Fayl adı"},
    "Type": {"ru": "Тип", "az": "Tip"},
    "Size": {"ru": "Размер", "az": "Ölçü"},
    "Recoverability": {"ru": "Восстановимость", "az": "Bərpa şansı"},
    "Opens": {"ru": "Открытие", "az": "Açılma"},
    "Partial": {"ru": "Частично", "az": "Yarımçıq"},
    "Select a file to preview": {"ru": "Выберите файл для просмотра",
                                 "az": "Önizləmə üçün fayl seçin"},
    "Preview": {"ru": "Предпросмотр", "az": "Önizləmə"},
    "No visual preview for this type": {"ru": "Нет визуального предпросмотра для этого типа",
                                        "az": "Bu tip üçün vizual önizləmə yoxdur"},
    "{n} selected": {"ru": "Выбрано: {n}", "az": "{n} seçildi"},
    "{n} file(s)": {"ru": "Файлов: {n}", "az": "{n} fayl"},
    "Showing {shown} of {total}": {"ru": "Показано {shown} из {total}",
                                   "az": "{total}-dan {shown} göstərilir"},
    "Showing first {shown} of {total}": {"ru": "Показаны первые {shown} из {total}",
                                         "az": "{total}-dan ilk {shown} göstərilir"},
    "New Scan": {"ru": "Новый скан", "az": "Yeni skan"},
    "Recover Selected": {"ru": "Восстановить выбранное", "az": "Seçilmişləri bərpa et"},
    # -- recovery destination ------------------------------------------
    "Recovery destination": {"ru": "Папка назначения", "az": "Bərpa yeri"},
    "Choose a SAFE folder on a DIFFERENT disk than the source.":
        {"ru": "Выберите БЕЗОПАСНУЮ папку на ДРУГОМ диске, не на источнике.",
         "az": "Mənbədən FƏRQLİ diskdə TƏHLÜKƏSİZ qovluq seçin."},
    "Select a destination folder...": {"ru": "Выберите папку назначения...",
                                       "az": "Təyinat qovluğunu seçin..."},
    "Browse...": {"ru": "Обзор...", "az": "Gözat..."},
    "Select recovery destination": {"ru": "Выберите папку для восстановления",
                                    "az": "Bərpa qovluğunu seçin"},
    "{n} file(s) selected   |   estimated size {size}":
        {"ru": "Выбрано файлов: {n}   |   примерный размер {size}",
         "az": "{n} fayl seçildi   |   təxmini ölçü {size}"},
    "{n} file(s)   |   need {need}   |   free {free}":
        {"ru": "Файлов: {n}   |   нужно {need}   |   свободно {free}",
         "az": "{n} fayl   |   lazım {need}   |   boş {free}"},
    "I understand the risk - allow recovery to the same disk (not recommended)":
        {"ru": "Я понимаю риск - разрешить восстановление на тот же диск (не рекомендуется)",
         "az": "Riski anlayıram - eyni diskə bərpaya icazə ver (tövsiyə olunmur)"},
    "DANGER: This destination is on the SOURCE disk. Writing here can overwrite the very data you are trying to recover. Choose another disk.":
        {"ru": "ОПАСНО: Эта папка на ДИСКЕ-ИСТОЧНИКЕ. Запись сюда может перезаписать восстанавливаемые данные. Выберите другой диск.",
         "az": "TƏHLÜKƏ: Bu yer MƏNBƏ diskdədir. Bura yazmaq bərpa etdiyiniz datanı üzərinə yaza bilər. Başqa disk seçin."},
    "Not enough free space: need {need}, only {free} available.":
        {"ru": "Недостаточно места: нужно {need}, доступно только {free}.",
         "az": "Boş yer çatmır: lazım {need}, yalnız {free} mövcuddur."},
    "Recovering...": {"ru": "Восстановление...", "az": "Bərpa edilir..."},
    "Recovery error: {msg}": {"ru": "Ошибка восстановления: {msg}", "az": "Bərpa xətası: {msg}"},
    # -- complete -------------------------------------------------------
    "Recovery complete": {"ru": "Восстановление завершено", "az": "Bərpa tamamlandı"},
    "Your files have been written to the destination folder.":
        {"ru": "Ваши файлы записаны в папку назначения.",
         "az": "Fayllarınız təyinat qovluğuna yazıldı."},
    "Recovered": {"ru": "Восстановлено", "az": "Bərpa olundu"},
    "Failed": {"ru": "Ошибки", "az": "Uğursuz"},
    "Written": {"ru": "Записано", "az": "Yazıldı"},
    "Destination": {"ru": "Назначение", "az": "Təyinat"},
    "Open Folder": {"ru": "Открыть папку", "az": "Qovluğu aç"},
    "Recover More Files": {"ru": "Восстановить ещё", "az": "Daha çox fayl bərpa et"},
    "Export Report": {"ru": "Экспорт отчёта", "az": "Hesabatı ixrac et"},
    "{n} file(s) were repaired so they open correctly.":
        {"ru": "Файлов восстановлено для корректного открытия: {n}.",
         "az": "{n} fayl düzgün açılması üçün bərpa edildi."},
    "{n} file(s) failed to recover.": {"ru": "Не удалось восстановить файлов: {n}.",
                                       "az": "{n} fayl bərpa olunmadı."},
    "{n} recovered file(s) still do not open (the original data was incomplete or overwritten).":
        {"ru": "Восстановленных файлов всё ещё не открываются: {n} (данные неполные или перезаписаны).",
         "az": "{n} bərpa olunan fayl hələ də açılmır (orijinal data natamam və ya üzərinə yazılıb)."},
    "See the activity log for details.": {"ru": "Подробности в журнале действий.",
                                          "az": "Təfərrüat üçün fəaliyyət jurnalına baxın."},
    # -- health ratings (devices.health_rating) ------------------------
    "Excellent": {"ru": "Отлично", "az": "Əla"},
    "Good": {"ru": "Хорошо", "az": "Yaxşı"},
    "Fair": {"ru": "Удовл.", "az": "Orta"},
    "Poor": {"ru": "Плохо", "az": "Zəif"},
    "Critical": {"ru": "Критично", "az": "Kritik"},
    "Average": {"ru": "Средне", "az": "Orta"},
    "Unknown": {"ru": "Неизв.", "az": "Naməlum"},
    "Close": {"ru": "Закрыть", "az": "Bağla"},
    "Sort: scan order": {"ru": "Сорт.: по порядку", "az": "Sıra: skan ardıcıllığı"},
    "Name": {"ru": "Имя", "az": "Ad"},
    "Largest": {"ru": "Сначала большие", "az": "Əvvəlcə böyük"},
    "Smallest": {"ru": "Сначала малые", "az": "Əvvəlcə kiçik"},
    "Openable first": {"ru": "Сначала открываемые", "az": "Əvvəlcə açılanlar"},
    "Format": {"ru": "Формат", "az": "Format"},
    "Dimensions": {"ru": "Размеры", "az": "Ölçülər"},
    "Confidence": {"ru": "Достоверность", "az": "Etibarlılıq"},
    "Offset": {"ru": "Смещение", "az": "Ofset"},
    "Yes - opens correctly": {"ru": "Да - открывается корректно", "az": "Bəli - düzgün açılır"},
    "Partially - opens but truncated": {"ru": "Частично - открывается, но обрезан",
                                        "az": "Qismən - açılır, amma yarımçıq"},
    "No - cannot be opened": {"ru": "Нет - не открывается", "az": "Xeyr - açılmır"},
    "Not checked for this type": {"ru": "Для этого типа не проверяется",
                                  "az": "Bu tip üçün yoxlanmır"},
    "[Image could not be decoded]": {"ru": "[Изображение не удалось декодировать]",
                                     "az": "[Şəkil dekod edilə bilmədi]"},
    "[Preview unavailable: {err}]": {"ru": "[Предпросмотр недоступен: {err}]",
                                     "az": "[Önizləmə əlçatmaz: {err}]"},
    "--- Content preview ---": {"ru": "--- Предпросмотр содержимого ---",
                                "az": "--- Məzmun önizləməsi ---"},
    # -- disk details window -------------------------------------------
    "{y} yr {d} d ({total} h)": {"en": "{y} yr {d} d ({total} h)",
                                 "ru": "{y} г {d} д ({total} ч)", "az": "{y} il {d} gün ({total} saat)"},
    "{d} d {h} h ({total} h)": {"en": "{d} d {h} h ({total} h)",
                                "ru": "{d} д {h} ч ({total} ч)", "az": "{d} gün {h} saat ({total} saat)"},
    "{h} h": {"en": "{h} h", "ru": "{h} ч", "az": "{h} saat"},
    "Disk info": {"ru": "Информация о диске", "az": "Disk məlumatı"},
    "Health (Health)": {"ru": "Здоровье (Health)", "az": "Sağlamlıq (Health)"},
    "Usage & lifetime": {"ru": "Использование и срок службы", "az": "İstifadə və ömür"},
    "Power-On time:": {"ru": "Время работы (Power-On):", "az": "İşləmə vaxtı (Power-On):"},
    "Temperature:": {"ru": "Температура:", "az": "Temperatur:"},
    "  (max {n} °C)": {"ru": "  (макс. {n} °C)", "az": "  (maks. {n} °C)"},
    "Lifetime writes:": {"ru": "Записано за всё время:", "az": "Ömür boyu yazılan:"},
    "SSD life left:": {"ru": "Остаток ресурса SSD:", "az": "SSD ömür qalığı:"},
    "Start/Stop cycles:": {"ru": "Циклы Start/Stop:", "az": "Start/Stop dövrü:"},
    "Manufacture date:": {"ru": "Дата производства:", "az": "İstehsal tarixi:"},
    "SMART attributes": {"ru": "Атрибуты SMART", "az": "SMART atributları"},
    "Problem attributes:": {"ru": "Проблемные атрибуты:", "az": "Problemli atributlar:"},
    "{n} item(s)": {"ru": "{n} шт.", "az": "{n} ədəd"},
    "value {v} / threshold {thr}": {"ru": "значение {v} / порог {thr}",
                                    "az": "dəyər {v} / hədd {thr}"},
    "Hardware information": {"ru": "Информация об оборудовании", "az": "Avadanlıq məlumatı"},
    "Capacity:": {"ru": "Объём:", "az": "Ölçü:"},
    "Used:": {"ru": "Использовано:", "az": "İstifadə olunan:"},
    "Manufacturer:": {"ru": "Производитель:", "az": "İstehsalçı:"},
    "Serial number:": {"ru": "Серийный номер:", "az": "Seriya nömrəsi:"},
    "Firmware:": {"ru": "Прошивка:", "az": "Firmware:"},
    "Bus type:": {"ru": "Тип шины:", "az": "Bus tipi:"},
    "Spindle speed:": {"ru": "Скорость вращения:", "az": "Fırlanma sürəti:"},
    "Partition style:": {"ru": "Стиль разделов:", "az": "Bölmə stili:"},
    "Sector size:": {"ru": "Размер сектора:", "az": "Sektor ölçüsü:"},
    "{n} bytes (logical)": {"ru": "{n} байт (логический)", "az": "{n} bayt (məntiqi)"},
    "Path:": {"ru": "Путь:", "az": "Yol:"},
    "Error counters": {"ru": "Счётчики ошибок", "az": "Xəta sayğacları"},
    "Read errors:": {"ru": "Ошибки чтения:", "az": "Oxuma xətaları:"},
    "Write errors:": {"ru": "Ошибки записи:", "az": "Yazma xətaları:"},
    "Partitions ({n})": {"ru": "Разделы ({n})", "az": "Bölmələr ({n})"},
    "Unnamed": {"ru": "Без имени", "az": "Adsız"},
    "Errors were detected on this disk. Copy important data to another disk immediately.":
        {"ru": "На этом диске обнаружены ошибки. Немедленно скопируйте важные данные на другой диск.",
         "az": "Bu diskdə xətalar aşkarlandı. Vacib məlumatları dərhal başqa bir diskə kopyalayın."},
    "WARNING: The disk reports it will fail soon (failure predicted). Copy your data immediately.":
        {"ru": "ВНИМАНИЕ: Диск сообщает о скором выходе из строя (failure predicted). Немедленно скопируйте данные.",
         "az": "DİQQƏT: Disk öz SMART sistemi ilə yaxın zamanda sıradan çıxacağını bildirir (failure predicted). Məlumatları dərhal köçürün."},
    "Note: raw SMART could not be read for this disk (not possible on some USB bridges).":
        {"ru": "Примечание: не удалось прочитать SMART для этого диска (невозможно на некоторых USB-мостах).",
         "az": "Qeyd: Bu disk üçün xam SMART məlumatı oxunmadı (bəzi USB körpülərində mümkün deyil)."},
    "If Reallocated / Pending / Uncorrectable sectors are above 0, the disk is degrading - back up now.":
        {"ru": "Если Reallocated / Pending / Uncorrectable секторы выше 0, диск деградирует - сделайте резервную копию.",
         "az": "Reallocated / Pending / Uncorrectable sektorlar 0-dan böyükdürsə, disk zədələnir - dərhal ehtiyat nüsxə götürün."},
    "health_status_good":
        {"en": "The disk is in good condition. No problem or weak sectors were found.",
         "ru": "Диск в хорошем состоянии. Проблемных или слабых секторов не найдено.",
         "az": "Diskin vəziyyəti yaxşıdır. Problemli və ya zəif sektor tapılmadı."},
    "health_status_warn":
        {"en": "Caution: wear or weak sectors were detected. Back up important data.",
         "ru": "Внимание: обнаружен износ или слабые секторы. Сделайте резервную копию важных данных.",
         "az": "DİQQƏT: Diskdə aşınma və ya zəif sektorlar aşkarlandı. Mühüm məlumatların ehtiyat nüsxəsini götürün."},
    "health_status_bad":
        {"en": "CRITICAL: the disk risks failure. Copy all important data to another disk IMMEDIATELY and retire this disk.",
         "ru": "КРИТИЧНО: диск рискует выйти из строя. НЕМЕДЛЕННО скопируйте все важные данные на другой диск и выведите этот диск из эксплуатации.",
         "az": "KRİTİK: Disk sıradan çıxma riski daşıyır. Bütün vacib məlumatları DƏRHAL başqa bir diskə köçürün və bu diski istifadədən çıxarın."},
    "basis_nvme": {"en": "  Health is based on the NVMe life indicator (Percentage Used).",
                   "ru": "  Здоровье рассчитано по индикатору ресурса NVMe (Percentage Used).",
                   "az": "  Sağlamlıq NVMe ömür göstəricisi (Percentage Used) əsasında hesablanıb."},
    "basis_231": {"en": "  Health is based on the SSD life indicator (#231).",
                  "ru": "  Здоровье рассчитано по индикатору ресурса SSD (#231).",
                  "az": "  Sağlamlıq SSD ömür göstəricisi (#231) əsasında hesablanıb."},
    "basis_problem": {"en": "  Health is based on problem SMART attributes.",
                      "ru": "  Здоровье рассчитано по проблемным атрибутам SMART.",
                      "az": "  Sağlamlıq problemli SMART atributları əsasında hesablanıb."},
    "basis_smart": {"en": "  Health is based on SMART attributes.",
                    "ru": "  Здоровье рассчитано по атрибутам SMART.",
                    "az": "  Sağlamlıq SMART atributları əsasında hesablanıb."},
    "about_body": {
        "en": "Recoverix runs fully offline. It never uploads your files, sends telemetry, "
              "or writes to the source disk.\n\nLimitations:\n"
              "- Recovery is never guaranteed.\n"
              "- Overwritten data cannot be recovered.\n"
              "- SSD TRIM may make deleted data unrecoverable.\n"
              "- Physically damaged drives may require a lab.\n"
              "- Fragmented large files may recover only partially.\n\n"
              "Logs and history are stored locally and can be cleared from the database folder.",
        "ru": "Recoverix работает полностью офлайн. Он не загружает ваши файлы, не отправляет "
              "телеметрию и не пишет на диск-источник.\n\nОграничения:\n"
              "- Восстановление не гарантируется.\n"
              "- Перезаписанные данные восстановить нельзя.\n"
              "- SSD TRIM может сделать удалённые данные невосстановимыми.\n"
              "- Физически повреждённые диски могут требовать лаборатории.\n"
              "- Фрагментированные большие файлы могут восстановиться лишь частично.\n\n"
              "Логи и история хранятся локально и могут быть очищены из папки базы данных.",
        "az": "Recoverix tam offline işləyir. Fayllarınızı yükləmir, telemetriya göndərmir "
              "və mənbə diskə yazmır.\n\nMəhdudiyyətlər:\n"
              "- Bərpa heç vaxt zəmanətli deyil.\n"
              "- Üzərinə yazılmış data bərpa oluna bilməz.\n"
              "- SSD TRIM silinmiş datanı bərpa olunmaz edə bilər.\n"
              "- Fiziki zədəli disklər laboratoriya tələb edə bilər.\n"
              "- Parçalanmış böyük fayllar yalnız qismən bərpa oluna bilər.\n\n"
              "Loglar və tarixçə lokal saxlanılır və verilənlər bazası qovluğundan silinə bilər."},
    "scan_error_body": {
        "en": "Could not scan the source.\n\n{err}\n\n"
              "Physical disks require running Recoverix as Administrator.",
        "ru": "Не удалось просканировать источник.\n\n{err}\n\n"
              "Для физических дисков запустите Recoverix от имени администратора.",
        "az": "Mənbə skan edilə bilmədi.\n\n{err}\n\n"
              "Fiziki disklər üçün Recoverix-i Administrator kimi işə salın."},
}


def _lookup(text: str) -> str:
    entry = _TR.get(text)
    if entry is None:
        return text
    if _lang == "en":
        return entry.get("en", text)
    return entry.get(_lang) or entry.get("en", text)


def set_language(code: str) -> None:
    global _lang
    if code in _CODE_TO_NAME:
        _lang = code


def current() -> str:
    return _lang


def current_name() -> str:
    return _CODE_TO_NAME.get(_lang, "English")


def code_for_name(name: str) -> str:
    return _NAME_TO_CODE.get(name, "en")


def t(text: str, **fmt) -> str:
    s = _lookup(text)
    return s.format(**fmt) if fmt else s
