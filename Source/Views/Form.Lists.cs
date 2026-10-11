using System;
using System.Collections.Generic;
using System.Linq;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.Primitives;
using Avalonia.Layout;
using Avalonia.Media;
using AudionAddressProcessor.Core;

namespace AudionAddressProcessor.Views;

/// <summary>
/// The lists that are data, not choices of the manifest: the sheets of the workbook a person
/// named, the headers of its first row. The engine builds them (`options` of address_cli.cmd, asked
/// through the process that stays up); the form asks when the field is drawn and again when the
/// field it depends on changes.
/// </summary>
public sealed partial class Form
{
    sealed class ListState
    {
        public List<Option> Options { get; set; } = new();
        public bool Loading { get; set; }
        public string Error { get; set; } = "";
        public List<Action> Repaint { get; } = new();
        public Field Field { get; init; } = new();
    }

    /// <summary>The lists of the fields of the form built now, by the key of the field.</summary>
    readonly Dictionary<string, ListState> _lists = new();

    /// <summary>The generation of the build: an answer that comes for a form long gone is dropped.</summary>
    int _ticket;

    ListState StateOf(Field field)
    {
        var key = Values.KeyOf(field);
        if (_lists.TryGetValue(key, out var held)) return held;
        var state = new ListState { Field = field };
        _lists[key] = state;
        Load(state);
        return state;
    }

    async void Load(ListState state)
    {
        if (_node is null) return;
        int ticket = _ticket;
        var node = _node;
        state.Loading = true;
        state.Error = "";
        foreach (var repaint in state.Repaint.ToArray()) repaint();
        List<Option> options;
        try { options = await _server.Options(node.Id, state.Field.Id, _values.ForDoor(node)); }
        catch (Exception ex)
        {
            options = new List<Option>();
            state.Error = ex.Message;
        }
        if (ticket != _ticket) return;
        state.Options = options;
        state.Loading = false;
        foreach (var repaint in state.Repaint.ToArray()) repaint();
    }

    /// <summary>A field changed: the lists that depend on it are asked for again, and the value chosen from the old one is dropped.</summary>
    void OnFieldChanged(Field changed)
    {
        foreach (var state in _lists.Values.ToArray())
        {
            if (!state.Field.DependsOn.Contains(changed.Id)) continue;
            _values.Reset(new[] { state.Field });
            Load(state);
        }
    }

    /// <summary>The source or the contents of the folders changed: the lists that look at them are read again.</summary>
    public void SourceChanged()
    {
        foreach (var state in _lists.Values.ToArray()) Load(state);
    }

    // ------------------------------------------------------------ a list under a line

    /// <summary>One value of a list the engine builds: a line that shows the choice and opens the list (<see cref="PickLine"/>).</summary>
    Control DataChoice(Field field)
    {
        var state = StateOf(field);
        var line = new PickLine(
            () => state.Options.Where(option => !option.Header).Select(option => new PickItem(option.Key, option.Name, option.Tip, option.IsPinned, option.Key.Length == 0)).ToList(),
            () => _values.Get(field),
            key => _values.Set(field, key), minWidth: 0, maxWidth: double.PositiveInfinity);
        if (field.Tip.Length > 0) ToolTip.SetTip(line.Button, field.Tip);
        void Repaint()
        {
            line.Repaint(state.Loading, state.Error);
            if (state.Error.Length == 0 && field.Tip.Length > 0) ToolTip.SetTip(line.Button, field.Tip);
        }
        state.Repaint.Add(Repaint);
        Watch(field, Repaint);
        return line.Button;
    }

    // ------------------------------------------------------------ for a panel that is not a form

    /// <summary>A panel of its own (the OKTMO keys) draws some fields of an operation itself: it takes the operation here first.</summary>
    public void Attach(Node node)
    {
        Forget();
        _node = node;
    }

    /// <summary>The line of a list that is data, for a panel.</summary>
    public Control DataLine(Field field)
    {
        Built.Add(field.Id);
        return DataChoice(field);
    }

    /// <summary>The box of a text field, for a panel.</summary>
    public Control TextLine(Field field)
    {
        Built.Add(field.Id);
        var cell = new StackPanel { Classes = { "cell" } };
        cell.Children.Add(Mark(field));
        cell.Children.Add(Label(field));
        var box = TextBox(field);
        box.Width = 330;
        cell.Children.Add(box);
        return cell;
    }

    /// <summary>A group of flags whose list the engine builds (the sheets of a workbook): ticks drawn again when the list comes.</summary>
    Control ListFlags(Field field)
    {
        var state = StateOf(field);
        var host = new WrapPanel { Orientation = Orientation.Horizontal };

        void Repaint()
        {
            host.Children.Clear();
            if (state.Loading) { host.Children.Add(new TextBlock { Classes = { "note" }, Text = Lang.T("читаю…") }); return; }
            var picked = _values.Picked(field);
            foreach (var option in state.Options)
            {
                // A line the engine puts in place of the list ("choose the workbook first") has no value to tick.
                if (option.Key.Length == 0)
                {
                    host.Children.Add(new TextBlock { Classes = { "note" }, Text = option.Name });
                    continue;
                }
                var flag = Tick(option.Caption);
                flag.Margin = new Thickness(0, 0, 3, 3);
                flag.IsChecked = picked.Contains(option.Key);
                var key = option.Key;
                flag.Click += (_, _) =>
                {
                    var now = _values.Picked(field);
                    if (flag.IsChecked == true) now.Add(key); else now.Remove(key);
                    // The order of the list, not of the clicks.
                    _values.Set(field, string.Join(Values.ListSeparator, state.Options.Select(item => item.Key).Where(now.Contains)));
                };
                host.Children.Add(flag);
            }
            if (state.Error.Length > 0) host.Children.Add(new TextBlock { Classes = { "note" }, Text = Lang.F("не прочитать: {0}", state.Error) });
        }
        state.Repaint.Add(Repaint);
        Watch(field, Repaint);
        return host;
    }
}
