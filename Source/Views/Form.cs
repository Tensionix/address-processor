using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.Primitives;
using Avalonia.Input;
using Avalonia.Layout;
using Avalonia.Media;
using Avalonia.Platform.Storage;
using AudionAddressProcessor.Core;
using Shapes = Avalonia.Controls.Shapes;

namespace AudionAddressProcessor.Views;

/// <summary>
/// The form of an operation, drawn by the keys of the manifest. A field is one cell - a mark that
/// its value is not the default, its name, its control - and cells flow in rows inside the frame
/// of their group. Choices of a few are a row of switches, never a drop-down list; a list that is
/// data (the sheets of a workbook, the headers of its first row) opens under its line.
/// The form keeps nothing itself: every control reads and writes <see cref="Values"/> by its field,
/// so the same field shown in two operations is one value.
/// </summary>
public sealed partial class Form
{
    readonly Values _values;
    readonly Window _owner;
    readonly Server _server;
    readonly Func<Manifest?> _manifest;

    Node? _node;

    /// <summary>What repaints the controls of a field, by the key of the field: a form built now, gone at the next build.</summary>
    readonly Dictionary<string, List<Action>> _cells = new();

    /// <summary>The cells and frames that hide while their field is not in sight.</summary>
    readonly List<(Control Cell, Field Field)> _shown = new();
    readonly List<(Control Frame, List<Control> Cells)> _frames = new();

    /// <summary>
    /// A panel that draws some fields itself (the OKTMO keys) hears every change of a value here: its
    /// buttons of pins follow the region and the municipality.
    /// </summary>
    public Action<Field>? FieldChanged { get; set; }

    /// <summary>Kinds of field met while building that the form cannot draw.</summary>
    public List<string> Unknown { get; } = new();

    /// <summary>The ids of the fields that got a control since the last <see cref="Forget"/>: what the self-check counts.</summary>
    public HashSet<string> Built { get; } = new();

    public Form(Values values, Window owner, Server server, Func<Manifest?> manifest)
    {
        _values = values;
        _owner = owner;
        _server = server;
        _manifest = manifest;
        _values.Changed += field =>
        {
            if (_cells.TryGetValue(Values.KeyOf(field), out var repaint))
                foreach (var action in repaint.ToArray()) action();
            OnFieldChanged(field);
            RefreshShown();
            FieldChanged?.Invoke(field);
        };
    }

    /// <summary>A new build of the left zone begins: the controls of the last one are forgotten.</summary>
    public void Forget()
    {
        _cells.Clear();
        _shown.Clear();
        _frames.Clear();
        _lists.Clear();
        Built.Clear();
        _ticket++;
    }

    void Watch(Field field, Action repaint)
    {
        var key = Values.KeyOf(field);
        if (!_cells.TryGetValue(key, out var list)) _cells[key] = list = new List<Action>();
        list.Add(repaint);
        repaint();
    }

    // ------------------------------------------------------------ the block names

    /// <summary>The name of a group of fields, as the form writes it over the frame.</summary>
    public static string GroupTitle(string id) => id switch
    {
        "files" => "ФАЙЛЫ",
        "sheets" => "ЛИСТЫ",
        "addresses" => "АДРЕСА",
        "rows" => "СТРОКИ",
        "columns" => "КОЛОНКИ",
        "parameters" => "ПАРАМЕТРЫ",
        "source" => "ИСТОЧНИК",
        "options" => "ОПЦИИ",
        "alignment_mode" => "РЕЖИМ",
        "related_columns" => "СВЯЗАННЫЕ КОЛОНКИ",
        "alignment_normalization" => "НОРМАЛИЗАЦИЯ",
        "territory" => "ТЕРРИТОРИЯ",
        _ => id.Replace('_', ' ').ToUpper(CultureInfo.CurrentCulture),
    };

    // ------------------------------------------------------------ groups

    /// <summary>
    /// The fields in their groups: framed, the frames in columns as many as the width holds (a frame
    /// that holds the line of the address takes the whole width); then, under a rule of their own,
    /// the fields the manifest calls advanced - always in sight, not folded away.
    /// </summary>
    public Control Build(Node node)
    {
        Forget();
        _node = node;
        var host = new GroupGrid { MinColumn = 380, Gap = 8 };
        var ordinary = node.Groups()
            .Select(group => (group.Id, Fields: group.Fields.Where(field => !field.Advanced).ToList()))
            .Where(group => group.Fields.Count > 0).ToList();
        foreach (var (id, fields) in ordinary)
        {
            var cells = new List<Control>();
            var inner = new StackPanel();
            // A frame of one field is named by the field itself: its title would say the same twice.
            if (fields.Count > 1 || fields[0].Kind == "slot_order")
                inner.Children.Add(new TextBlock { Classes = { "grouptitle" }, Text = Lang.T(GroupTitle(id)) });
            inner.Children.Add(Rows(fields, cells));
            var frame = new Border { Classes = { "group" }, Child = inner };
            GroupGrid.SetWide(frame, fields.Any(field => field.Kind is "slot_order" or "slot_preview"));
            _frames.Add((frame, cells));
            host.Children.Add(frame);
        }
        var advanced = node.FormFields.Where(field => field.Advanced).ToList();
        if (advanced.Count > 0)
        {
            var cells = new List<Control>();
            var rule = new Grid { ColumnDefinitions = new ColumnDefinitions("Auto,*"), Margin = new Thickness(0, 6, 0, 6) };
            rule.Children.Add(new TextBlock { Classes = { "grouptitle" }, Text = Lang.T("ДОПОЛНИТЕЛЬНО"), Margin = new Thickness(0, 0, 10, 0) });
            var line = new Border { Classes = { "hsep" }, Height = 1, BorderThickness = new Thickness(0, 1, 0, 0), VerticalAlignment = VerticalAlignment.Center };
            Grid.SetColumn(line, 1);
            rule.Children.Add(line);
            var body = Rows(advanced, cells);
            // Inset as far as the text inside the frames above: a frame's border and its padding.
            var section = new StackPanel { Margin = new Thickness(10, 0, 10, 0), Children = { rule, body } };
            GroupGrid.SetWide(section, true);
            _frames.Add((section, cells));
            host.Children.Add(section);
        }
        RefreshShown();
        return host;
    }

    /// <summary>Whatever is not in sight now (its conditions are not met) hides; a frame with nothing in it hides too.</summary>
    public void RefreshShown()
    {
        if (_node is null) return;
        foreach (var (cell, field) in _shown) cell.IsVisible = _values.IsShown(_node, field);
        foreach (var (frame, cells) in _frames) frame.IsVisible = cells.Count == 0 || cells.Any(cell => cell.IsVisible);
    }

    /// <summary>
    /// The fields of a group as a table: a name and its control in a row - the names of the group in one
    /// column, the controls in the other, stretched - and the flags (the ones that need no name) in
    /// columns of equal width. The slots of the address are one control above the rest.
    /// </summary>
    StackPanel Rows(List<Field> fields, List<Control> cells)
    {
        var rows = new StackPanel { Spacing = 6 };
        Grid.SetIsSharedSizeScope(rows, true);
        var slots = fields.Where(field => field.Kind is "slot_order" or "slot_preview").ToList();
        var enabled = fields.FirstOrDefault(field => field.Kind == "checkboxes" && field.Id == "enabled_slots");
        var rest = fields;
        if (slots.Count > 0 && enabled is not null && slots.Any(field => field.Kind == "slot_order"))
        {
            var ladder = SlotLadder(slots.FirstOrDefault(field => field.Kind == "slot_preview"), enabled, slots.First(field => field.Kind == "slot_order"));
            foreach (var field in slots.Concat(new[] { enabled })) Built.Add(field.Id);
            cells.Add(ladder);
            _shown.Add((ladder, enabled));
            rows.Children.Add(ladder);
            rest = fields.Where(field => !slots.Contains(field) && field != enabled).ToList();
        }
        FlagGrid? flags = null;
        foreach (var field in rest)
        {
            if (!FieldKinds.Known.Contains(field.Kind))
            {
                Unknown.Add($"{field.Id}: {field.Kind}");
                continue;
            }
            Built.Add(field.Id);
            if (field.Kind == "checkbox")
            {
                // Flags that stand one after another make one table.
                if (flags is null) rows.Children.Add(flags = new FlagGrid { MaxColumns = 3 });
                // The mark of a changed value lies over the flag's right edge: no flag is pushed from the left edge of the frame.
                var overMark = Mark(field);
                overMark.HorizontalAlignment = HorizontalAlignment.Right;
                overMark.Margin = new Thickness(0, 0, 9, 0);
                overMark.IsHitTestVisible = false;
                var flagCell = new Grid { Classes = { "flagcell" }, Children = { Flag(field), overMark } };
                flags.Children.Add(flagCell);
                cells.Add(flagCell);
                _shown.Add((flagCell, field));
                continue;
            }
            flags = null;
            var row = LabelRow(field);
            rows.Children.Add(row);
            cells.Add(row);
            _shown.Add((row, field));
        }
        return rows;
    }

    // ------------------------------------------------------------ cells

    Shapes.Ellipse Mark(Field field)
    {
        var mark = new Shapes.Ellipse { Classes = { "changed" } };
        ToolTip.SetTip(mark, Lang.T("Значение отличается от умолчания манифеста."));
        Watch(field, () => mark.Opacity = _values.IsChanged(field) ? 1 : 0);
        return mark;
    }

    TextBlock Label(Field field)
    {
        var label = new TextBlock { Classes = { "flabel" }, Text = field.Caption, TextWrapping = TextWrapping.Wrap, MaxWidth = 230, VerticalAlignment = VerticalAlignment.Center };
        if (field.Tip.Length > 0) ToolTip.SetTip(label, field.Tip);
        return label;
    }

    /// <summary>A field with a name: the name in the column all the names of the frame share, the control in the other.</summary>
    Control LabelRow(Field field)
    {
        // A choice or a set of flags is wider than a row of a table: its name stands over it.
        if (field.Kind is "radio" or "checkboxes" || (field.Kind == "select" && !field.HasProvider)) return StackedRow(field);
        var row = new Grid { MinHeight = 28 };
        row.ColumnDefinitions.Add(new ColumnDefinition(GridLength.Auto) { SharedSizeGroup = "name" });
        row.ColumnDefinitions.Add(new ColumnDefinition(GridLength.Star));
        var name = new StackPanel { Orientation = Orientation.Horizontal, VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(0, 0, 12, 0) };
        name.Children.Add(Label(field));
        name.Children.Add(Mark(field));
        row.Children.Add(name);

        Control body;
        switch (field.Kind)
        {
            case "number":
            {
                var box = NumberBox(field);
                box.Width = 110;
                box.HorizontalAlignment = HorizontalAlignment.Left;
                body = box;
                break;
            }
            case "select":
                body = DataChoice(field);
                break;
            case "xlsx_file_picker":
            {
                var line = new Grid { ColumnDefinitions = new ColumnDefinitions("*,Auto") };
                line.Children.Add(TextBox(field));
                var browse = BrowseButton(field);
                browse.Margin = new Thickness(6, 0, 0, 0);
                Grid.SetColumn(browse, 1);
                line.Children.Add(browse);
                body = line;
                break;
            }
            case "slot_preview":
                body = new TextBlock { Classes = { "slotpreview" }, TextWrapping = TextWrapping.Wrap, Text = Values.DefaultOf(field), VerticalAlignment = VerticalAlignment.Center };
                break;
            default:
                body = TextBox(field);
                break;
        }
        Grid.SetColumn(body, 1);
        row.Children.Add(body);
        return row;
    }

    /// <summary>A field whose control is wider than a cell of the table: the name over it, the control under it across the frame.</summary>
    Control StackedRow(Field field)
    {
        var name = new StackPanel { Orientation = Orientation.Horizontal, Margin = new Thickness(0, 2, 0, 3) };
        name.Children.Add(Label(field));
        name.Children.Add(Mark(field));
        Control body = field.Kind switch
        {
            "checkboxes" => field.HasProvider ? ListFlags(field) : FlagTable(Flags(field)),
            _ => Row(Choice(field), wrap: true),
        };
        return new StackPanel { Children = { name, body } };
    }

    /// <summary>Flags as a table: equal columns, as many as the longest name allows.</summary>
    static FlagGrid FlagTable(IEnumerable<Control> flags)
    {
        var table = new FlagGrid { MaxColumns = 3 };
        foreach (var flag in flags)
        {
            flag.HorizontalAlignment = HorizontalAlignment.Stretch;
            if (flag is ContentControl content) content.HorizontalContentAlignment = HorizontalAlignment.Left;
            table.Children.Add(flag);
        }
        return table;
    }

    static Panel Row(IEnumerable<Control> controls, bool wrap = false)
    {
        Panel row = wrap ? new WrapPanel { Orientation = Orientation.Horizontal } : new StackPanel { Orientation = Orientation.Horizontal };
        foreach (var control in controls)
        {
            if (control is ToggleButton button) button.Margin = new Thickness(0, 0, 3, wrap ? 3 : 0);
            row.Children.Add(control);
        }
        return row;
    }

    // ------------------------------------------------------------ controls

    /// <summary>A flag as a switch of the program with a small tick box: the height and the font of every other switch.</summary>
    static ToggleButton Tick(string text)
    {
        var box = new Border
        {
            Classes = { "tickbox" },
            Child = new Shapes.Path { Classes = { "tick" }, Data = Geometry.Parse("M 1.5,5 L 4,7.5 L 8.5,2.5") },
        };
        return new ToggleButton
        {
            Classes = { "switch" },
            Content = new StackPanel
            {
                Orientation = Orientation.Horizontal, Spacing = 6,
                Children = { box, new TextBlock { Text = text, VerticalAlignment = VerticalAlignment.Center } },
            },
        };
    }

    ToggleButton Flag(Field field)
    {
        var flag = Tick(field.Caption);
        if (field.Tip.Length > 0) ToolTip.SetTip(flag, field.Tip);
        flag.Click += (_, _) => _values.Set(field, flag.IsChecked == true ? "true" : "false");
        Watch(field, () => flag.IsChecked = _values.IsOn(field));
        return flag;
    }

    /// <summary>A choice of a few: a row of switches, one of them on.</summary>
    List<Control> Choice(Field field)
    {
        var buttons = new List<(ToggleButton Button, string Key)>();
        foreach (var option in field.Options.Where(option => !option.Header))
        {
            var button = new ToggleButton { Classes = { "switch" }, Content = option.Caption };
            var tip = option.Tip.Length > 0 ? option.Tip : option.Caption == option.Name ? field.Tip : field.Tip.Length > 0 ? option.Name + " - " + field.Tip : option.Name;
            if (tip.Length > 0) ToolTip.SetTip(button, tip);
            var key = option.Key;
            button.Click += (_, _) =>
            {
                _values.Set(field, key);
                // A press on the chosen one must not switch it off: one of the row is always on.
                button.IsChecked = _values.Get(field) == key;
            };
            buttons.Add((button, key));
        }
        Watch(field, () =>
        {
            var current = _values.Get(field);
            foreach (var (button, key) in buttons) button.IsChecked = key == current;
        });
        return buttons.Select(item => (Control)item.Button).ToList();
    }

    /// <summary>A group of flags: each on or off, the value is the list of those that are on, in the order of the manifest.</summary>
    List<Control> Flags(Field field)
    {
        var flags = new List<(ToggleButton Flag, string Key)>();
        foreach (var option in field.Options.Where(option => !option.Header))
        {
            var flag = Tick(option.Caption);
            var tip = option.Tip.Length > 0 ? option.Tip : field.Tip;
            if (tip.Length > 0) ToolTip.SetTip(flag, tip);
            flags.Add((flag, option.Key));
        }
        foreach (var (flag, _) in flags)
            flag.Click += (_, _) => _values.Set(field, string.Join(Values.ListSeparator, flags.Where(item => item.Flag.IsChecked == true).Select(item => item.Key)));
        Watch(field, () =>
        {
            var picked = _values.Picked(field);
            foreach (var (flag, key) in flags) flag.IsChecked = picked.Contains(key);
        });
        return flags.Select(item => (Control)item.Flag).ToList();
    }

    TextBox TextBox(Field field)
    {
        var box = new TextBox { Classes = { "field" }, PlaceholderText = field.PlaceholderText };
        if (field.Tip.Length > 0) ToolTip.SetTip(box, field.Tip);
        box.TextChanged += (_, _) => _values.Set(field, box.Text ?? "");
        // The box a person types in is not rewritten under the cursor: only a value that came from elsewhere is put in.
        Watch(field, () => { if ((box.Text ?? "") != _values.Get(field)) box.Text = _values.Get(field); });
        return box;
    }

    /// <summary>
    /// A number: typed, or stepped with the arrow keys; kept inside min and max of the manifest.
    /// What is not a number is not taken - the box goes back to the value it had.
    /// </summary>
    TextBox NumberBox(Field field)
    {
        var box = new TextBox { Classes = { "field", "number" } };
        var keys = Lang.T("Стрелки вверх и вниз меняют значение.");
        ToolTip.SetTip(box, field.Tip.Length > 0 ? field.Tip + "\n" + keys : keys);
        double step = field.Step is { } given && given > 0 ? given : 1;

        void Take()
        {
            var typed = (box.Text ?? "").Trim().Replace(',', '.');
            // Not a number a run can take: NaN and infinity parse, and cannot be written down for the command.
            if (double.TryParse(typed, NumberStyles.Float, CultureInfo.InvariantCulture, out var number) && double.IsFinite(number)) _values.Set(field, Fit(field, number));
            box.Text = _values.Get(field);
        }
        void Move(int direction)
        {
            if (!double.TryParse(_values.Get(field), NumberStyles.Float, CultureInfo.InvariantCulture, out var number)) number = 0;
            // Rounded to the step's own digits: 0.1 added ten times is 1, not 0.9999999999999999.
            _values.Set(field, Fit(field, Math.Round(number + direction * step, 6)));
        }
        box.LostFocus += (_, _) => Take();
        box.KeyDown += (_, e) =>
        {
            if (e.Key == Key.Enter) { Take(); e.Handled = true; }
            else if (e.Key == Key.Up) { Take(); Move(1); e.Handled = true; }
            else if (e.Key == Key.Down) { Take(); Move(-1); e.Handled = true; }
        };
        Watch(field, () => { if (!box.IsFocused || (box.Text ?? "") != _values.Get(field)) box.Text = _values.Get(field); });
        return box;
    }

    static string Fit(Field field, double number)
    {
        if (field.Min is { } min && number < min) number = min;
        if (field.Max is { } max && number > max) number = max;
        return number.ToString("0.######", CultureInfo.InvariantCulture);
    }

    /// <summary>A workbook is picked with the dialog of the system: the line stays editable, the button is only a way to fill it.</summary>
    Button BrowseButton(Field field)
    {
        var button = new Button { Classes = { "tool", "io" }, Content = Icons.Sign("folder-open") };
        ToolTip.SetTip(button, Lang.T("Выбрать книгу Excel."));
        button.Click += async (_, _) =>
        {
            var options = new FilePickerOpenOptions
            {
                Title = field.Name, AllowMultiple = false,
                FileTypeFilter = new[]
                {
                    new FilePickerFileType(Lang.T("Книги Excel")) { Patterns = new[] { "*.xlsx", "*.xlsm", "*.xls" } },
                    new FilePickerFileType(Lang.T("Все файлы")) { Patterns = new[] { "*" } },
                },
            };
            try
            {
                // Where the dialog opens: beside the file named now.
                var current = Paths.Full(_values.Get(field));
                var folder = current.Length > 0 && Directory.Exists(Path.GetDirectoryName(current)) ? Path.GetDirectoryName(current) : null;
                if (folder is not null) options.SuggestedStartLocation = await _owner.StorageProvider.TryGetFolderFromPathAsync(folder);
            }
            catch { }
            var picked = await _owner.StorageProvider.OpenFilePickerAsync(options);
            if (picked.Count > 0 && picked[0].TryGetLocalPath() is { } path) _values.Set(field, path);
        };
        return button;
    }
}
