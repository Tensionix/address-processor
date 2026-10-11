using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.Primitives;
using Avalonia.Layout;
using AudionAddressProcessor.Core;
using AudionAddressProcessor.Views;

namespace AudionAddressProcessor;

/// <summary>
/// The sections of the layout as a band of big buttons under the header, the operations of the
/// chosen section as a second band over the form, and the card of the chosen operation: its name,
/// what it does, the button that runs it, its form. The window knows no section and no operation
/// by name - they come from config\window_layout.yaml and config\tool_manifest.yaml.
/// </summary>
public partial class MainWindow
{
    SectionInfo? _section;
    Node? _node;
    readonly Dictionary<string, string> _lastOperation = new();

    /// <summary>Every button that starts an operation: all of them wait while one runs.</summary>
    readonly List<Button> _runButtons = new();

    static string Upper(string text) => text.ToUpper(CultureInfo.CurrentCulture);

    // ------------------------------------------------------------ the sections

    void BuildSections()
    {
        SectionRow.Children.Clear();
        SectionRow.ColumnDefinitions.Clear();
        OpRow.Children.Clear();
        if (_manifest is null) return;
        foreach (var section in _manifest.Layout.Sections)
        {
            var head = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 7, HorizontalAlignment = HorizontalAlignment.Center };
            if (Icons.Glyph(section.Icon) is not null) head.Children.Add(Icons.Sign(section.Icon));
            head.Children.Add(new TextBlock { Classes = { "sectionname" }, Text = Upper(section.Name) });
            var face = new StackPanel { VerticalAlignment = VerticalAlignment.Center, Children = { head } };
            // A line that does not fit - a larger font, a narrow window - ends in an ellipsis, not at the rim.
            if (section.Line.Length > 0) face.Children.Add(new TextBlock { Classes = { "hint" }, Text = section.Line, TextTrimming = Avalonia.Media.TextTrimming.CharacterEllipsis, HorizontalAlignment = HorizontalAlignment.Center });
            var tab = new ToggleButton { Classes = { "switch", "section" }, Tag = section.Id, Content = face, HorizontalAlignment = HorizontalAlignment.Stretch, MinHeight = 46 };
            Avalonia.Automation.AutomationProperties.SetAutomationId(tab, "section_" + section.Id);
            ToolTip.SetTip(tab, section.Name + "\n" + section.Line);
            tab.Click += (_, _) => SelectSection(section);
            // The sections share the width of the window equally, with a gap between them.
            if (SectionRow.ColumnDefinitions.Count > 0) SectionRow.ColumnDefinitions.Add(new ColumnDefinition(new GridLength(6)));
            SectionRow.ColumnDefinitions.Add(new ColumnDefinition(GridLength.Star));
            Grid.SetColumn(tab, SectionRow.ColumnDefinitions.Count - 1);
            SectionRow.Children.Add(tab);
        }
        var open = _manifest.Layout.Sections.FirstOrDefault(section => section.Id == _section?.Id) ?? _manifest.Layout.Sections.FirstOrDefault();
        if (open is not null) SelectSection(open);
        Lang.Walk(SectionRow);
    }

    void SelectSection(SectionInfo section)
    {
        _section = section;
        foreach (var child in SectionRow.Children)
            if (child is ToggleButton tab) tab.IsChecked = (string?)tab.Tag == section.Id;

        // The operations of the section: a band of switches as large as the sections over it. A name
        // that does not fit an equal share takes its own width (Views\EvenRow.cs).
        OpRow.Children.Clear();
        foreach (var placed in section.Operations)
        {
            var node = _manifest?.Find(placed.Id);
            if (node is null) continue;
            var face = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 7, HorizontalAlignment = HorizontalAlignment.Center };
            var sign = placed.Icon.Length > 0 ? placed.Icon : "";
            if (Icons.Glyph(sign) is not null) face.Children.Add(Icons.Sign(sign));
            var name = placed.TabName.Length > 0 ? placed.TabName : node.Name;
            face.Children.Add(new TextBlock { Classes = { "sectionname" }, Text = Upper(name), TextTrimming = Avalonia.Media.TextTrimming.CharacterEllipsis });
            var tab = new ToggleButton { Classes = { "switch", "section" }, Tag = placed.Id, Content = face, HorizontalAlignment = HorizontalAlignment.Stretch };
            Avalonia.Automation.AutomationProperties.SetAutomationId(tab, $"operation_{section.Id}_{placed.Id}");
            ToolTip.SetTip(tab, node.Name + (node.About.Length > 0 ? "\n" + node.About : ""));
            tab.Click += (_, _) => SelectOperation(placed);
            OpRow.Children.Add(tab);
        }
        // A section of one operation has nothing to switch.
        OpBar.IsVisible = section.Operations.Count > 1;
        var chosen = section.Operations.FirstOrDefault(placed => _lastOperation.TryGetValue(section.Id, out var last) && last == placed.Id) ?? section.Operations.FirstOrDefault();
        if (chosen is not null) SelectOperation(chosen);
        Lang.Walk(OpRow);
    }

    void SelectOperation(PlacedOperation placed)
    {
        if (_section is not null) _lastOperation[_section.Id] = placed.Id;
        foreach (var child in OpRow.Children)
            if (child is ToggleButton tab) tab.IsChecked = (string?)tab.Tag == placed.Id;
        var node = _manifest?.Find(placed.Id);
        if (node is null) return;
        _node = node;
        ShowCard(node);
    }

    // ------------------------------------------------------------ the card

    /// <summary>The card of an operation: its name and what it does, the button that runs it, its form.</summary>
    void ShowCard(Node node)
    {
        Cards.Children.Clear();
        _runButtons.RemoveAll(button => button.Tag as string == "card");
        CardsNote.IsVisible = false;
        _form.Forget();

        var head = new Grid { ColumnDefinitions = new ColumnDefinitions("*,Auto"), Margin = new Thickness(0, 0, 0, 8) };
        var titles = new StackPanel { VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(0, 0, 12, 0) };
        titles.Children.Add(new TextBlock { Classes = { "optitle" }, Text = node.Name, TextWrapping = Avalonia.Media.TextWrapping.Wrap });
        if (node.About.Length > 0)
        {
            var about = new TextBlock { Classes = { "opabout" }, Text = node.About, TextWrapping = Avalonia.Media.TextWrapping.Wrap, MaxLines = 2, TextTrimming = Avalonia.Media.TextTrimming.CharacterEllipsis };
            ToolTip.SetTip(about, node.About);
            titles.Children.Add(about);
        }
        head.Children.Add(titles);

        // The main button of the card: filled with the accent, white letters, at the right end, no sign
        // and no description - the description is in the tooltip. A dangerous operation is burnt orange.
        var run = new Button { Classes = { "step", "fill" }, Tag = "card", Height = 32, MinHeight = 32, VerticalAlignment = VerticalAlignment.Center, Content = new TextBlock { Text = Lang.T("ЗАПУСТИТЬ") } };
        run.Classes.Set("burn", node.Kind == "dangerous");
        Avalonia.Automation.AutomationProperties.SetAutomationId(run, "run_" + node.Id);
        ToolTip.SetTip(run, node.Name + (node.About.Length > 0 ? "\n" + node.About : "") + "\n\n" + Lang.T("Ctrl+Enter - запустить открытую операцию."));
        run.Click += (_, _) => Press(node);
        Grid.SetColumn(run, 1);
        head.Children.Add(run);
        _runButtons.Add(run);
        _withButton.Add(node.Id);
        run.IsEnabled = !_runner.Running;

        var card = new Border { Classes = { "opcard" } };
        var body = new StackPanel { Children = { head } };
        if (node.Fields.Any(field => field.Kind == "oktmo_key_toolbar")) body.Children.Add(OktmoPanel(node));
        else if (node.FormFields.Any()) body.Children.Add(_form.Build(node));
        else body.Children.Add(new TextBlock { Classes = { "note" }, TextWrapping = Avalonia.Media.TextWrapping.Wrap, Text = Lang.T("У этой операции нет параметров: она работает с источником и назначением, названными справа.") });
        card.Child = body;
        Cards.Children.Add(card);
        if (_form.Unknown.Count > 0)
            Journal.Add(Lang.F("[окно] поля неизвестного вида не показаны: {0}", string.Join("; ", _form.Unknown)));
        Lang.Walk(Cards);
    }

    /// <summary>The operation of the card in sight, or null.</summary>
    Node? CardOperation() => _node is { Runs: true } node ? node : null;

    // ------------------------------------------------------------ the buttons that stand outside the bands

    /// <summary>
    /// The operations the layout places beside the working folders (the check of the source) and under
    /// the result (the cleanup of an empty row, the archive): a small button each, with its sign.
    /// </summary>
    void BuildService()
    {
        IoButtons.Children.Clear();
        ResultActions.Children.Clear();
        _runButtons.RemoveAll(button => button.Tag as string == "direct");
        if (_manifest is null) return;
        if (_manifest.Find(_manifest.Layout.Workspace.Check) is { } check)
            IoButtons.Children.Add(Direct(check, Lang.T("ПРОВЕРИТЬ")));
        foreach (var id in _manifest.Layout.ResultActions)
            if (_manifest.Find(id) is { } node)
                ResultActions.Children.Add(Direct(node, Upper(node.Name)));
        BuildServiceMenu();
    }

    Button Direct(Node node, string caption)
    {
        var face = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 6 };
        if (_manifest!.Layout.Icons.TryGetValue(node.Id, out var sign) && Icons.Glyph(sign) is not null) face.Children.Add(Icons.Sign(sign));
        face.Children.Add(new TextBlock { Text = caption });
        var button = new Button { Classes = { "small", "word" }, Tag = "direct", Content = face, Margin = new Thickness(0, 0, 4, 4) };
        button.Classes.Set("burn", node.Kind == "dangerous");
        Avalonia.Automation.AutomationProperties.SetAutomationId(button, "run_" + node.Id);
        ToolTip.SetTip(button, node.Name + (node.About.Length > 0 ? "\n" + node.About : ""));
        button.Click += (_, _) => Press(node);
        button.IsEnabled = !_runner.Running;
        _runButtons.Add(button);
        _withButton.Add(node.Id);
        return button;
    }
}
