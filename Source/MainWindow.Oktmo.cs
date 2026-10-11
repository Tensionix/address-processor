using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Layout;
using Avalonia.Media;
using AudionAddressProcessor.Core;
using AudionAddressProcessor.Views;

namespace AudionAddressProcessor;

/// <summary>
/// The panel of the OKTMO keys: the region and the municipality (each can be pinned, and added to the
/// key file whole), the search of a settlement by its name, the file of the keys the address
/// normaliser narrows its search with, and the file of the pins. It is not a form of the manifest -
/// it is what the toolbar field (`oktmo_key_toolbar`) stands for; the fields of that operation
/// (region, municipality, the folder of the data) are drawn in it as they are, by the same form.
///
/// Every action is one question to the process of the engine that stays up (address_cli.cmd serve):
/// the window decides nothing about keys. The panel of the window before this one called the
/// service in its own process; its seventeen calls are the seventeen actions asked here.
/// </summary>
public partial class MainWindow
{
    /// <summary>What the panel keeps beside the fields of the manifest: the query, the candidates found, the row chosen.</summary>
    readonly Dictionary<string, string> _oktmo = new();
    List<Option> _candidates = new();
    Node? _oktmoNode;

    // The controls of the panel built now, repainted as the answers come.
    Button? _pinRegion, _unpinRegion, _addRegion, _pinCity, _unpinCity, _addCity, _addFound;
    TextBlock? _keysSummary, _pinsSummary, _foundSummary, _registryLine;
    WrapPanel? _keyList;
    Button? _copyKeys;
    TextBlock? _keysHead;
    TextBox? _foundPreview;
    PickLine? _foundLine;
    string _keyText = "";

    Field? OktmoField(Node node, string id) => node.Fields.FirstOrDefault(field => field.Id == id);

    /// <summary>The panel of an operation that has the toolbar of the OKTMO keys among its fields.</summary>
    Control OktmoPanel(Node node)
    {
        _form.Attach(node);
        _oktmoNode = node;
        _candidates = new List<Option>();
        foreach (var field in node.Fields.Where(field => field.Kind == "oktmo_key_toolbar")) _form.Built.Add(field.Id);
        var host = new GroupGrid { MinColumn = 380, Gap = 8 };
        var region = OktmoField(node, "oktmo_scope_region");
        var city = OktmoField(node, "oktmo_scope_municipality");

        // ---- the territory: region and municipality, the search of a settlement
        var territory = new StackPanel();
        territory.Children.Add(new TextBlock { Classes = { "grouptitle" }, Text = Lang.T("ТЕРРИТОРИЯ") });
        _registryLine = new TextBlock { Classes = { "note" }, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(2, 0, 0, 6) };
        territory.Children.Add(_registryLine);
        if (region is not null) territory.Children.Add(ScopeRow(node, region, "region", out _pinRegion, out _unpinRegion, out _addRegion));
        if (city is not null) territory.Children.Add(ScopeRow(node, city, "municipality", out _pinCity, out _unpinCity, out _addCity));

        territory.Children.Add(new TextBlock { Classes = { "flabel" }, Text = Lang.T("Поиск населённого пункта"), Margin = new Thickness(2, 10, 0, 3) });
        var query = new TextBox { Classes = { "field" }, PlaceholderText = Lang.T("Ключи, Мирный, 17-й километр"), Width = 330, Text = _oktmo.GetValueOrDefault("oktmo_settlement_query", "") };
        ToolTip.SetTip(query, Lang.T("Введите населённый пункт или муниципальный объект, затем нажмите поиск."));
        query.TextChanged += (_, _) => _oktmo["oktmo_settlement_query"] = query.Text ?? "";
        query.KeyDown += (_, e) => { if (e.Key == Avalonia.Input.Key.Enter) { e.Handled = true; FindCandidates(node); } };
        var find = OktmoButton("search", "НАЙТИ КАНДИДАТОВ", "Найти точные строки ОКТМО по названию.");
        find.Click += (_, _) => FindCandidates(node);
        territory.Children.Add(new WrapPanel { Children = { query, Gap(find) } });

        _foundLine = new PickLine(
            () => _candidates.Select(option => new PickItem(option.Key, option.Name, option.Tip, false, false)).ToList(),
            () => _oktmo.GetValueOrDefault("oktmo_candidate_ref", ""),
            key => { _oktmo["oktmo_candidate_ref"] = key; ShowFound(); }, minWidth: 330, maxWidth: 560);
        ToolTip.SetTip(_foundLine.Button, Lang.T("Выберите найденный населённый пункт или муниципальную строку."));
        _addFound = OktmoButton("plus", "ДОБАВИТЬ НАЙДЕННЫЕ НП", "Добавить выбранную строку в текущие ключи. Для всего МО используйте + в поле муниципалитета.");
        _addFound.Click += (_, _) => AddCandidateKeys(node);
        _foundLine.Button.Margin = new Thickness(0, 0, 0, 4);
        territory.Children.Add(new WrapPanel { Margin = new Thickness(0, 6, 0, 0), Children = { _foundLine.Button, Gap(_addFound) } });
        _foundPreview = new TextBox
        {
            Classes = { "field" }, IsReadOnly = true, AcceptsReturn = true, TextWrapping = TextWrapping.NoWrap, MinHeight = 76, MaxHeight = 140,
            Margin = new Thickness(0, 6, 0, 0), IsVisible = false,
        };
        territory.Children.Add(_foundPreview);
        _foundSummary = new TextBlock { Classes = { "note" }, Margin = new Thickness(2, 4, 0, 0), TextWrapping = TextWrapping.Wrap };
        territory.Children.Add(_foundSummary);
        var territoryFrame = new Border { Classes = { "group" }, Child = territory };
        GroupGrid.SetWide(territoryFrame, true);
        host.Children.Add(territoryFrame);

        // ---- the file of the keys
        var keys = new StackPanel();
        var head = new Grid { ColumnDefinitions = new ColumnDefinitions("*,Auto") };
        _keysHead = new TextBlock { Classes = { "grouptitle" }, Text = Lang.T("КЛЮЧИ") };
        head.Children.Add(_keysHead);
        var tools = new StackPanel { Orientation = Orientation.Horizontal };
        var copy = new Button { Classes = { "tool", "io" }, Content = Icons.Sign("copy") };
        ToolTip.SetTip(copy, Lang.T("Скопировать ключи в буфер обмена."));
        _copyKeys = copy;
        copy.Click += async (_, _) =>
        {
            if (_keyText.Length == 0) return;
            if (Clipboard is { } clipboard) await Avalonia.Input.Platform.ClipboardExtensions.SetTextAsync(clipboard, _keyText);
            Say("ключи ОКТМО скопированы", refused: false, passing: true);
        };
        var expand = new Button { Classes = { "tool", "io" }, Content = Icons.Sign("maximize-2") };
        ToolTip.SetTip(expand, Lang.T("Показать все ключи в отдельном окне."));
        expand.Click += (_, _) => ShowAllKeys();
        tools.Children.Add(copy);
        tools.Children.Add(expand);
        Grid.SetColumn(tools, 1);
        head.Children.Add(tools);
        keys.Children.Add(head);
        var keyButtons = new FlagGrid { MaxColumns = 2, Margin = new Thickness(0, 0, 0, 6) };
        foreach (var (sign, text, tip, action) in new[]
        {
            ("folder-open", "ОТКРЫТЬ", "Открыть файл текущих ключей в программе, которая открывает .txt.", "open_keys"),
            ("save", "СОХРАНИТЬ", "Записать ключи выбранных региона и муниципалитета в файл; без выбора - сохранить то, что в файле.", "save_keys"),
            ("upload", "ЗАГРУЗИТЬ", "Прочитать файл ключей заново.", "load_keys"),
            ("eraser", "ОЧИСТИТЬ", "Очистить файл текущих ключей. Пины остаются.", "clear_keys"),
            ("rotate-ccw", "СБРОСИТЬ КЛЮЧИ ОКТМО", "Очистить выбранный регион, муниципалитет, поиск НП и текущий файл ключей. Пины и сохранённые пути остаются.", "reset_keys"),
        })
        {
            var button = OktmoButton(sign, text, tip);
            button.Classes.Set("burn", action is "clear_keys" or "reset_keys");
            button.Click += (_, _) => KeyFileAction(node, action);
            keyButtons.Children.Add(button);
        }
        keys.Children.Add(keyButtons);
        _keysSummary = new TextBlock { Classes = { "note" }, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(2, 0, 0, 4) };
        keys.Children.Add(_keysSummary);
        _keyList = new WrapPanel();
        keys.Children.Add(new Border { Classes = { "listbox" }, MaxHeight = 190, Child = new ScrollViewer { HorizontalScrollBarVisibility = Avalonia.Controls.Primitives.ScrollBarVisibility.Disabled, Content = _keyList } });
        host.Children.Add(new Border { Classes = { "group" }, Child = keys });

        // ---- the file of the pins
        var pins = new StackPanel();
        pins.Children.Add(new TextBlock { Classes = { "grouptitle" }, Text = Lang.T("ПИНЫ ОКТМО") });
        var pinButtons = new FlagGrid { MaxColumns = 2, Margin = new Thickness(0, 0, 0, 6) };
        foreach (var (sign, text, tip, action) in new[]
        {
            ("folder-open", "ОТКРЫТЬ ПИНЫ", "Открыть файл пинов.", "pins_open"),
            ("save", "ЭКСПОРТ ПИНОВ", "Записать пины в файл output\\oktmo_pins и в сводный файл рядом с ключами.", "pins_export"),
            ("upload", "ИМПОРТ ПИНОВ", "Прочитать пины из последнего файла: input, корень программы или прежний экспорт. Пины добавляются к имеющимся.", "pins_import"),
            ("eraser", "ОЧИСТИТЬ ПИНЫ ОКТМО", "Снять все пины регионов и муниципалитетов.", "pins_clear"),
        })
        {
            var button = OktmoButton(sign, text, tip);
            button.Classes.Set("burn", action == "pins_clear");
            button.Click += (_, _) => PinFileAction(node, action);
            pinButtons.Children.Add(button);
        }
        pins.Children.Add(pinButtons);
        _pinsSummary = new TextBlock { Classes = { "note" }, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(2, 0, 0, 2) };
        pins.Children.Add(_pinsSummary);
        host.Children.Add(new Border { Classes = { "group" }, Child = pins });

        // ---- the folder of the data, always in sight
        if (OktmoField(node, "oktmo_data_dir") is { } dataDir)
        {
            var rule = new Grid { ColumnDefinitions = new ColumnDefinitions("Auto,*"), Margin = new Thickness(0, 6, 0, 6) };
            rule.Children.Add(new TextBlock { Classes = { "grouptitle" }, Text = Lang.T("ДОПОЛНИТЕЛЬНО"), Margin = new Thickness(0, 0, 10, 0) });
            var line = new Border { Classes = { "hsep" }, Height = 1, BorderThickness = new Thickness(0, 1, 0, 0), VerticalAlignment = VerticalAlignment.Center };
            Grid.SetColumn(line, 1);
            rule.Children.Add(line);
            var advanced = new StackPanel { Margin = new Thickness(10, 0, 10, 0), Children = { rule, _form.TextLine(dataDir) } };
            GroupGrid.SetWide(advanced, true);
            host.Children.Add(advanced);
        }

        // The pins of a line follow what the line holds; the lists of the engine follow the lines.
        _form.FieldChanged = changed =>
        {
            if (ReferenceEquals(_oktmoNode, _node) && (changed.Id == region?.Id || changed.Id == city?.Id)) RefreshScopeButtons(node);
        };
        ShowFound();
        RefreshOktmo();
        return host;
    }

    // ------------------------------------------------------------ the pieces

    Button OktmoButton(string sign, string text, string tip)
    {
        var face = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 6 };
        if (sign.Length > 0) face.Children.Add(Icons.Sign(sign));
        face.Children.Add(new TextBlock { Text = Lang.T(text) });
        var button = new Button { Classes = { "small", "word" }, Content = face, HorizontalAlignment = HorizontalAlignment.Stretch, HorizontalContentAlignment = HorizontalAlignment.Left };
        if (tip.Length > 0) ToolTip.SetTip(button, Lang.T(tip));
        return button;
    }

    static Control Gap(Control control)
    {
        control.Margin = new Thickness(6, 0, 0, 0);
        return control;
    }

    /// <summary>A line of the region or of the municipality: its name, the list, and the pin, the unpin and the "add its keys" buttons.</summary>
    Control ScopeRow(Node node, Field field, string kind, out Button pin, out Button unpin, out Button add)
    {
        var row = new Grid { ColumnDefinitions = new ColumnDefinitions("Auto,Auto,*,Auto"), Margin = new Thickness(0, 0, 4, 4), MinHeight = 28 };
        var label = new TextBlock { Classes = { "flabel" }, Text = field.Caption, MinWidth = 150 };
        if (field.Tip.Length > 0) ToolTip.SetTip(label, field.Tip);
        _form.Built.Add(field.Id);
        row.Children.Add(label);
        var choice = _form.DataLine(field);
        Grid.SetColumn(choice, 2);
        row.Children.Add(choice);
        var buttons = new StackPanel { Orientation = Orientation.Horizontal, Margin = new Thickness(6, 0, 0, 0) };
        pin = new Button { Classes = { "tool", "io" }, Content = Icons.Sign("pin") };
        unpin = new Button { Classes = { "tool", "io" }, Content = Icons.Sign("minus") };
        add = new Button { Classes = { "tool", "io" }, Content = Icons.Sign("plus") };
        // Shut until the engine says what the line holds: a button that looks alive and does nothing is worse than one that waits.
        pin.IsEnabled = unpin.IsEnabled = add.IsEnabled = false;
        ToolTip.SetTip(pin, Lang.T("Закрепить значение в списке выбора."));
        ToolTip.SetTip(unpin, Lang.T("Открепить значение из списка выбора."));
        ToolTip.SetTip(add, Lang.T("Добавить выбранный регион или МО в файл ключей поиска. Для МО добавляются формы МО и все НП внутри."));
        pin.Click += (_, _) => ScopeAction(node, kind, "pin_scope");
        unpin.Click += (_, _) => ScopeAction(node, kind, "unpin_scope");
        add.Click += (_, _) => ScopeAction(node, kind, "add_scope_keys");
        buttons.Children.Add(pin);
        buttons.Children.Add(unpin);
        buttons.Children.Add(add);
        Grid.SetColumn(buttons, 3);
        row.Children.Add(buttons);
        return row;
    }

    JsonObject OktmoValues(Node node)
    {
        var values = JsonNode.Parse(_values.ForDoor(node)) as JsonObject ?? new JsonObject();
        foreach (var (key, value) in _oktmo)
            if (key is "oktmo_settlement_query" or "oktmo_candidate_ref") values[key] = value;
        return values;
    }

    static int Count(JsonElement owner, string name) =>
        owner.ValueKind == JsonValueKind.Object && owner.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.Number ? value.GetInt32() : 0;

    static string Text(JsonElement owner, string name) =>
        owner.ValueKind == JsonValueKind.Object && owner.TryGetProperty(name, out var value) ? value.ValueKind == JsonValueKind.String ? value.GetString() ?? "" : value.ToString() : "";

    // ------------------------------------------------------------ what the panel shows

    /// <summary>The Rosstat data changed, or the panel was just drawn: the registry line, the keys and the pins are read again.</summary>
    void RefreshOktmo()
    {
        if (_oktmoNode is not { } node || !ReferenceEquals(_oktmoNode, _node)) return;
        ReadRegistry(node);
        ReadKeys(node);
        ReadPins(node);
        RefreshScopeButtons(node);
        _form.SourceChanged();
    }

    async void ReadRegistry(Node node)
    {
        if (_registryLine is null) return;
        try
        {
            var status = await _server.Oktmo("data_status", OktmoValues(node));
            if (!ReferenceEquals(node, _oktmoNode) || _registryLine is null) return;
            var ok = status.TryGetProperty("ok", out var flag) && flag.ValueKind == JsonValueKind.True;
            _registryLine.Text = ok ? Lang.F("Реестр Росстата: {0}", Text(status, "latest_name"))
                : Lang.F("Реестр Росстата не найден: {0}. Скачайте снимок во вкладке «ОБНОВИТЬ РОССТАТ».", Text(status, "rosstat_dir"));
            _registryLine.Classes.Set("warn", !ok);
        }
        catch (Exception ex) { if (_registryLine is not null) _registryLine.Text = Lang.F("не прочитать: {0}", ex.Message); }
    }

    async void ReadKeys(Node node)
    {
        try { ShowKeys(await _server.Oktmo("load_keys")); }
        catch (Exception ex) { Say(ex.Message, refused: true); }
    }

    void ShowKeys(JsonElement result)
    {
        if (_keyList is null || _keysSummary is null || _keysHead is null) return;
        var items = new List<string>();
        if (result.ValueKind == JsonValueKind.Object && result.TryGetProperty("items", out var list) && list.ValueKind == JsonValueKind.Array)
            items.AddRange(list.EnumerateArray().Select(item => item.ToString()).Where(item => item.Trim().Length > 0));
        _keyText = string.Join("\n", items);
        if (_copyKeys is not null) _copyKeys.IsEnabled = items.Count > 0;
        _keysHead.Text = Lang.F("КЛЮЧИ ({0})", items.Count);
        _keysSummary.Text = Lang.F("{0} ключей: {1}", Count(result, "keys"), Paths.Short(Text(result, "path")));
        _keyList.Children.Clear();
        // A region has thousands of settlements: the panel shows the first of them, the window of all of them shows the rest.
        foreach (var item in items.Take(400))
        {
            var tag = new Border { Classes = { "tag" }, Margin = new Thickness(0, 0, 4, 4), Child = new TextBlock { Text = item } };
            ToolTip.SetTip(tag, item);
            _keyList.Children.Add(tag);
        }
        if (items.Count > 400) _keyList.Children.Add(new TextBlock { Classes = { "note" }, Text = Lang.F("… и ещё {0}: кнопка «развернуть» выше", items.Count - 400) });
        if (items.Count == 0) _keyList.Children.Add(new TextBlock { Classes = { "note" }, Text = Lang.T("Ключи пока не загружены."), Margin = new Thickness(4) });
    }

    async void ReadPins(Node node)
    {
        try
        {
            var status = await _server.Oktmo("pins_status");
            if (_pinsSummary is not null)
                _pinsSummary.Text = Lang.F("Пинов: регионов {0}, МО {1}: {2}", Count(status, "regions"), Count(status, "municipalities"), Paths.Short(Text(status, "path")));
        }
        catch (Exception ex) { Say(ex.Message, refused: true); }
    }

    /// <summary>The buttons of a line follow what the line holds: nothing chosen - nothing to pin; chosen but not pinned - nothing to unpin.</summary>
    async void RefreshScopeButtons(Node node)
    {
        foreach (var (kind, pin, unpin, add) in new[] { ("region", _pinRegion, _unpinRegion, _addRegion), ("municipality", _pinCity, _unpinCity, _addCity) })
        {
            if (pin is null || unpin is null || add is null) continue;
            try
            {
                var status = await _server.Oktmo("scope_pin_status", OktmoValues(node), kind);
                if (!ReferenceEquals(node, _oktmoNode)) return;
                bool has = Text(status, "value").Length > 0, pinned = status.TryGetProperty("pinned", out var p) && p.ValueKind == JsonValueKind.True;
                pin.IsEnabled = has;
                pin.Classes.Set("on", pinned);
                unpin.IsEnabled = has && pinned;
                add.IsEnabled = has;
            }
            catch { pin.IsEnabled = unpin.IsEnabled = add.IsEnabled = false; }
        }
    }

    void ShowFound()
    {
        if (_foundPreview is null || _foundSummary is null || _addFound is null || _foundLine is null) return;
        var preview = _oktmo.GetValueOrDefault("oktmo_candidate_preview", "");
        _foundPreview.Text = preview;
        _foundPreview.IsVisible = preview.Length > 0;
        var parts = new[]
        {
            _oktmo.GetValueOrDefault("oktmo_selected_municipality", "") is { Length: > 0 } municipality ? Lang.F("МО: {0}", municipality) : "",
            _oktmo.GetValueOrDefault("oktmo_selected_settlement", "") is { Length: > 0 } settlement ? Lang.F("НП: {0}", settlement) : "",
            _oktmo.GetValueOrDefault("oktmo_selected_code", "") is { Length: > 0 } code ? Lang.F("ОКТМО: {0}", code) : "",
        }.Where(part => part.Length > 0);
        _foundSummary.Text = string.Join(" | ", parts);
        _addFound.IsEnabled = _oktmo.GetValueOrDefault("oktmo_candidate_ref", "").Length > 0 && _candidates.Any(option => option.Key == _oktmo["oktmo_candidate_ref"]);
        _foundLine.Repaint();
        _foundLine.Button.IsEnabled = _candidates.Count > 0;
    }

    // ------------------------------------------------------------ the actions

    /// <summary>One action of the panel: asked of the engine, answered in words, the panel read again. Not while an operation runs.</summary>
    async Task<JsonElement?> Ask(Node node, string action, string kind = "region", bool withValues = true)
    {
        if (_runner.Running) { Say("идёт другая операция", refused: true); return null; }
        try
        {
            // The values are taken before the question: the panel may change while the engine thinks.
            var values = withValues ? OktmoValues(node) : null;
            return await _server.Oktmo(action, values, kind);
        }
        catch (Exception ex)
        {
            Say(ex.Message, refused: true);
            return null;
        }
    }

    void Told(string who, string message)
    {
        Journal.Add($"OKTMO {who}: {message}");
        Say(message, refused: false, passing: true);
    }

    /// <summary>The engine named fields to put right after an action (the region a found settlement belongs to, what was chosen).</summary>
    void ApplyUpdates(Node node, JsonElement result)
    {
        if (result.ValueKind != JsonValueKind.Object || !result.TryGetProperty("field_updates", out var updates) || updates.ValueKind != JsonValueKind.Object) return;
        foreach (var update in updates.EnumerateObject())
        {
            if (update.Name == "oktmo_candidate_options")
            {
                _candidates = update.Value.ValueKind == JsonValueKind.Array
                    ? update.Value.EnumerateArray().Select(item => System.Text.Json.JsonSerializer.Deserialize<Option>(item.GetRawText(), new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower, PropertyNameCaseInsensitive = true }) ?? new Option()).ToList()
                    : new List<Option>();
                continue;
            }
            var text = update.Value.ValueKind == JsonValueKind.String ? update.Value.GetString() ?? "" : update.Value.ToString();
            if (OktmoField(node, update.Name) is { } field) _values.Set(field, text);
            else _oktmo[update.Name] = text;
        }
    }

    async void ScopeAction(Node node, string kind, string action)
    {
        var who = Lang.T(kind == "region" ? "регион" : "муниципалитет");
        if (action == "add_scope_keys") Say("добавляю ключи ОКТМО…", refused: false, passing: true);
        if (await Ask(node, action, kind) is not { } result) return;
        Told(who, action switch
        {
            "pin_scope" => Lang.T("Закреплено."),
            "unpin_scope" => Lang.T("Откреплено."),
            _ => Lang.F("Добавлено ключей: {0}. Всего в файле: {1}.", Count(result, "added"), Count(result, "keys")),
        });
        if (action != "add_scope_keys")
        {
            // The pin changed the order of the lists: they are asked for again.
            await _server.ForgetOptions();
            _form.SourceChanged();
        }
        ReadKeys(node);
        RefreshScopeButtons(node);
    }

    async void FindCandidates(Node node)
    {
        _oktmo["oktmo_candidate_preview"] = Lang.T("Идёт поиск…");
        _oktmo["oktmo_candidate_ref"] = "";
        _candidates = new List<Option>();
        ShowFound();
        if (await Ask(node, "find_candidates") is not { } result)
        {
            _oktmo["oktmo_candidate_preview"] = "";
            ShowFound();
            return;
        }
        ApplyUpdates(node, result);
        ShowFound();
        Told(Lang.T("кандидат"), Lang.F("Найдено кандидатов ОКТМО: {0}.", Count(result, "count")));
    }

    async void AddCandidateKeys(Node node)
    {
        if (await Ask(node, "add_candidate_keys") is not { } result) return;
        ApplyUpdates(node, result);
        ShowFound();
        Told(Lang.T("кандидат"), Lang.F("Добавлено ключей по найденному НП: {0}. Всего в файле: {1}.", Count(result, "added"), Count(result, "keys")));
        ReadKeys(node);
        RefreshScopeButtons(node);
    }

    async void KeyFileAction(Node node, string action)
    {
        if (await Ask(node, action, withValues: action == "save_keys") is not { } result) return;
        var path = Paths.Short(Text(result, "path"));
        var keys = Count(result, "keys") > 0 ? Count(result, "keys") : Count(result, "saved");
        Told(Lang.T("ключи"), action switch
        {
            "save_keys" => Lang.F("Ключи сохранены: {0}. {1}", keys, path),
            "load_keys" => Lang.F("Ключи загружены: {0}. {1}", keys, path),
            "clear_keys" => Lang.T("Ключи очищены."),
            "reset_keys" => Lang.T("Ключи ОКТМО сброшены. Регион, муниципалитет и поиск НП очищены."),
            "open_keys" => Lang.F("Файл ключей открыт: {0}", path),
            _ => Lang.T("Готово."),
        });
        if (action == "reset_keys")
        {
            ApplyUpdates(node, result);
            // What the service lists as cleared: the region, the municipality and the search of the panel.
            foreach (var id in new[] { "oktmo_scope_region", "oktmo_scope_municipality" })
                if (OktmoField(node, id) is { } field) _values.Set(field, "");
            foreach (var key in new[] { "oktmo_settlement_query", "oktmo_candidate_ref", "oktmo_candidate_preview", "oktmo_selected_municipality", "oktmo_selected_settlement", "oktmo_selected_code" }) _oktmo[key] = "";
            _candidates = new List<Option>();
            ShowFound();
            // The text box of the search takes the cleared value when the card is drawn again.
            if (ReferenceEquals(_node, node)) ShowCard(node);
            return;
        }
        ReadKeys(node);
    }

    async void PinFileAction(Node node, string action)
    {
        // The pins are set by hand and nothing keeps a copy: one press must not take them all.
        if (action == "pins_clear")
        {
            var go = await Dialog.Ask(this, "Очистить пины ОКТМО?",
                new[] { "Будут сняты все закрепления регионов и муниципалитетов.", "Вернуть их можно только импортом из ранее выгруженного файла." },
                "ОЧИСТИТЬ", Tone.Danger);
            if (go is null) return;
        }
        if (await Ask(node, action, withValues: false) is not { } result) return;
        var path = Paths.Short(Text(result, "path"));
        Told(Lang.T("пины"), action switch
        {
            "pins_open" => Lang.F("Файл пинов открыт: {0}", path),
            "pins_export" => Lang.F("Пины экспортированы: регионов {0}, МО {1}. {2}", Count(result, "regions"), Count(result, "municipalities"), path),
            "pins_import" => Lang.F("Пины импортированы: регионов {0}, МО {1}. {2}", Count(result, "regions"), Count(result, "municipalities"), path),
            "pins_clear" => Lang.T("Пины очищены."),
            _ => Lang.T("Готово."),
        });
        if (action is "pins_import" or "pins_clear")
        {
            await _server.ForgetOptions();
            _form.SourceChanged();
        }
        ReadPins(node);
        RefreshScopeButtons(node);
    }

    /// <summary>Every key in a window of its own, with the copy button: the panel itself shows the first of them.</summary>
    void ShowAllKeys()
    {
        var window = new Window
        {
            Title = Lang.F("Ключи ОКТМО ({0})", _keyText.Length == 0 ? 0 : _keyText.Split('\n').Length), Width = 640, Height = 640,
            WindowStartupLocation = WindowStartupLocation.CenterOwner, ShowInTaskbar = false,
            Background = App.Ink("AppBg"), Foreground = App.Ink("TextMain"),
            FontFamily = (FontFamily?)(Application.Current?.FindResource("FontGrid")) ?? FontFamily.Default, FontSize = 12,
        };
        var box = new TextBox { Text = _keyText, IsReadOnly = true, AcceptsReturn = true, TextWrapping = TextWrapping.NoWrap, Margin = new Thickness(10) };
        var copy = new Button { Content = Lang.T("СКОПИРОВАТЬ"), MinHeight = 30, Margin = new Thickness(10, 0, 4, 10) };
        copy.Click += async (_, _) => { if (window.Clipboard is { } clipboard) await Avalonia.Input.Platform.ClipboardExtensions.SetTextAsync(clipboard, _keyText); };
        var close = new Button { Content = Lang.T("ЗАКРЫТЬ"), MinHeight = 30, Margin = new Thickness(0, 0, 10, 10), IsCancel = true };
        close.Click += (_, _) => window.Close();
        var bottom = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right, Children = { copy, close } };
        var grid = new Grid { RowDefinitions = new RowDefinitions("*,Auto") };
        grid.Children.Add(box);
        Grid.SetRow(bottom, 1);
        grid.Children.Add(bottom);
        window.Content = grid;
        window.ShowDialog(this);
    }
}
