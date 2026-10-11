using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.RegularExpressions;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.Primitives;
using Avalonia.Input;
using Avalonia.Layout;
using Avalonia.Media;
using Microsoft.Win32;
using Ellipse = Avalonia.Controls.Shapes.Ellipse;
using AudionAddressProcessor.Core;

namespace AudionAddressProcessor;

/// <summary>
/// ABOUT, the way the other Audion windows have it: a button at the right of the header opens a
/// sheet in place of the sections; the same button, the cross or Esc brings the sections back. The
/// header also holds what the machine has for the program - the Rosstat registry, Excel, Word - as
/// small badges, and the service menu: the folders of the program and the cleanup of its own.
/// </summary>
public partial class MainWindow
{
    string _sheet = "";

    void WireSheets()
    {
        SheetAbout.Click += (_, _) => ToggleSheet("about");
        SheetClose.Click += (_, _) => { if (_sheet.Length > 0) ToggleSheet(_sheet); };
        AddHandler(KeyDownEvent, (_, e) =>
        {
            if (e.Key != Key.Escape || _sheet.Length == 0) return;
            e.Handled = true;
            ToggleSheet(_sheet);
        }, Avalonia.Interactivity.RoutingStrategies.Tunnel);
    }

    void ToggleSheet(string key)
    {
        _sheet = _sheet == key ? "" : key;
        SheetAbout.IsChecked = _sheet == "about";
        bool open = _sheet.Length > 0;
        SectionRow.IsVisible = Zones.IsVisible = !open;
        SheetHost.IsVisible = open;
        FillSheet();
        if (!open) Shell.Focus();
    }

    /// <summary>The sheet in sight is written again: the language changed.</summary>
    void FillSheet()
    {
        SheetBody.Children.Clear();
        _into = null;
        if (_sheet == "about") FillAbout();
        else return;
        if (Lang.Code != "ru") Lang.Walk(SheetBody);
    }

    // ------------------------------------------------------------ what a sheet is put together of

    /// <summary>Open starts a card with a name; Add, Note and Pair go into it until the next Open.</summary>
    Panel? _into;

    void Add(Control control) => (_into ?? SheetBody).Children.Add(control);

    void Head(string text) => SheetBody.Children.Add(new TextBlock
    {
        Text = text, FontWeight = FontWeight.SemiBold, FontSize = 16, Margin = new Thickness(0, 0, 0, 8),
    });

    void OpenCard(string title)
    {
        var body = new StackPanel { Spacing = 2 };
        body.Children.Add(new TextBlock { Text = title, Classes = { "caption" }, Margin = new Thickness(0, 0, 0, 4) });
        SheetBody.Children.Add(new Border { Classes = { "subcard" }, Margin = new Thickness(0, 0, 0, 8), Child = body });
        _into = body;
    }

    void Note(string text) => Add(new TextBlock { Text = text, Classes = { "note" }, TextWrapping = TextWrapping.Wrap });

    void Pair(string key, string value, string? open = null)
    {
        var row = new Grid { ColumnDefinitions = new ColumnDefinitions("150,*,Auto") };
        row.Children.Add(new TextBlock { Text = key, Classes = { "caption" }, VerticalAlignment = VerticalAlignment.Top, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 0, 10, 0) });
        var shown = new SelectableTextBlock { Text = value, TextWrapping = TextWrapping.Wrap };
        Grid.SetColumn(shown, 1);
        row.Children.Add(shown);
        if (open is not null)
        {
            var button = new Button { Classes = { "tool" }, Content = Icons.Sign("folder-open"), Margin = new Thickness(6, 0, 0, 0) };
            ToolTip.SetTip(button, Lang.T("Открыть в проводнике."));
            button.Click += (_, _) => Open(open);
            Grid.SetColumn(button, 2);
            row.Children.Add(button);
        }
        Add(row);
    }

    // ------------------------------------------------------------ ABOUT

    void FillAbout()
    {
        Head("ABOUT");
        OpenCard("ПРОГРАММА");
        Pair("Название", AppTitle);
        Pair("Версия", Paths.Version);
        Pair("Окно", "Avalonia 12 · .NET " + Environment.Version.Major);
        Pair("Движок", Paths.Python.Length > 0 ? Paths.Python : Lang.T("не найден: соберите окружение, builder_main.cmd"));
        Pair("Консольная команда", Paths.Door);

        OpenCard("ПАПКИ");
        Pair("Программа", Paths.Root, Paths.Root);
        var folders = _manifest?.Paths;
        Pair("input", folders?.Input is { Length: > 0 } input ? input : Path.Combine(Paths.Root, "input"), folders?.Input);
        Pair("output", folders?.Output is { Length: > 0 } output ? output : Path.Combine(Paths.Root, "output"), folders?.Output);
        Pair("logs", folders?.Logs is { Length: > 0 } logs ? logs : Path.Combine(Paths.Root, "logs"), folders?.Logs);
        Pair("report", folders?.Report is { Length: > 0 } report ? report : Path.Combine(Paths.Root, "report"), folders?.Report);
        Pair("config", Paths.ProjectConfig, Paths.ProjectConfig);

        OpenCard("АВТОР И ЛИЦЕНЗИЯ");
        Pair("Автор", "Audion");
        Pair("Лицензия", "Apache License 2.0");
        Note("Имя и знак Audion принадлежат автору и не передаются производным работам (TRADEMARK.md). Лицензии сторонних компонентов лежат в папке licenses рядом с программой.");
    }

    // ------------------------------------------------------------ the service menu

    /// <summary>The service menu: the folders of the program, and the cleanup of its own folders when the layout offers one.</summary>
    void BuildServiceMenu()
    {
        var items = new MenuFlyout { Placement = PlacementMode.BottomEdgeAlignedRight };
        MenuItem Folder(string title, string path, string sign)
        {
            var item = new MenuItem { Header = Lang.T(title), Icon = Icons.Sign(sign) };
            item.Click += (_, _) => Open(path);
            return item;
        }
        items.Items.Add(Folder("Папка программы", Paths.Root, "folder-open"));
        items.Items.Add(Folder("input", _manifest?.Paths.Input is { Length: > 0 } input ? input : Path.Combine(Paths.Root, "input"), "folder"));
        items.Items.Add(Folder("output", _manifest?.Paths.Output is { Length: > 0 } output ? output : Path.Combine(Paths.Root, "output"), "folder"));
        items.Items.Add(Folder("logs", _manifest?.Paths.Logs is { Length: > 0 } logs ? logs : Path.Combine(Paths.Root, "logs"), "scroll-text"));
        items.Items.Add(Folder("report", _manifest?.Paths.Report is { Length: > 0 } report ? report : Path.Combine(Paths.Root, "report"), "scroll-text"));
        items.Items.Add(Folder("config", Paths.ProjectConfig, "settings"));
        if (_manifest?.Find(_manifest.Layout.Workspace.Clear) is { } clear)
        {
            items.Items.Add(new Separator());
            var item = new MenuItem { Header = Lang.T("Очистить input и output программы (операция)"), Icon = Icons.Sign("eraser") };
            ToolTip.SetTip(item, clear.Name + (clear.About.Length > 0 ? "\n" + clear.About : ""));
            item.Click += (_, _) => Press(clear);
            items.Items.Add(item);
            _withButton.Add(clear.Id);
        }
        ServiceButton.Flyout = items;
    }

    // ------------------------------------------------------------ what the machine has for the program

    /// <summary>
    /// The badges of the header: the snapshot of the Rosstat registry the OKTMO keys are made of, and
    /// whether the machine has Excel and Word (the transfer of columns and the comparison drive Excel;
    /// the conversion of old .doc files drives Word).
    /// </summary>
    async void BuildBadges()
    {
        BadgeRow.Children.Clear();
        var registry = Badge("ОКТМО", Lang.T("читаю снимок Росстата…"), "dot");
        BadgeRow.Children.Add(registry.Box);
        BadgeRow.Children.Add(Machine("Excel", "Excel.Application", "Нужен для переноса колонок и сравнения двух таблиц."));
        BadgeRow.Children.Add(Machine("Word", "Word.Application", "Нужен для конвертации старых .doc."));
        Lang.Walk(BadgeRow);
        try
        {
            var status = await _server.Oktmo("data_status");
            var name = status.TryGetProperty("latest_name", out var n) ? n.GetString() ?? "" : "";
            var found = Regex.Match(name, @"data-(\d{4})(\d{2})(\d{2})");
            if (found.Success && DateTime.TryParseExact(found.Groups[1].Value + found.Groups[2].Value + found.Groups[3].Value, "yyyyMMdd", null, System.Globalization.DateTimeStyles.None, out var date))
            {
                registry.Set(date.ToString("dd.MM.yyyy"), (DateTime.Today - date).TotalDays > 400 ? "warn" : "ok",
                    Lang.F("Снимок реестра ОКТМО Росстата: {0}\nПо нему строятся ключи территории. Обновляется в разделе ОКТМО.", name));
            }
            else registry.Set(Lang.T("нет снимка"), "bad", Lang.T("В папке data\\rosstat нет файла data-*.csv: ключи ОКТМО не построить. Обновите снимок в разделе ОКТМО."));
        }
        catch (Exception ex) { registry.Set("?", "bad", ex.Message); }
    }

    sealed class BadgeFace
    {
        public Border Box { get; init; } = new();
        public Ellipse Dot { get; init; } = new();
        public TextBlock Value { get; init; } = new();
        public void Set(string value, string tone, string tip)
        {
            Value.Text = value;
            foreach (var known in new[] { "ok", "warn", "bad" }) Dot.Classes.Set(known, known == tone);
            ToolTip.SetTip(Box, tip);
        }
    }

    static BadgeFace Badge(string name, string value, string tone)
    {
        var dot = new Ellipse { Classes = { "dot" } };
        var text = new TextBlock { Text = value, VerticalAlignment = VerticalAlignment.Center };
        var box = new Border
        {
            Classes = { "spec" }, Margin = new Thickness(0, 0, 6, 0),
            Child = new StackPanel
            {
                Orientation = Orientation.Horizontal, Spacing = 6,
                Children = { dot, new TextBlock { Text = Lang.T(name), Classes = { "caption" }, VerticalAlignment = VerticalAlignment.Center }, text },
            },
        };
        return new BadgeFace { Box = box, Dot = dot, Value = text };
    }

    /// <summary>A program of Office the machine has: found by its COM class in the registry.</summary>
    static Control Machine(string name, string progId, string why)
    {
        bool there = false;
        try { using var key = Registry.ClassesRoot.OpenSubKey(progId + @"\CLSID"); there = key is not null; } catch { }
        var face = Badge(name, there ? "✓" : "—", "");
        face.Set(there ? "✓" : "—", there ? "ok" : "bad",
            there ? Lang.T(why) : Lang.F("{0} не найден на этой машине. {1}", name, Lang.T(why)));
        return face.Box;
    }
}
