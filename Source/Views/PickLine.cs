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

/// <summary>One line of a list that is data: the key it keeps, its name, what it says in a tooltip, whether it is pinned, whether it only stands for "nothing chosen".</summary>
public sealed record PickItem(string Key, string Name, string Tip, bool Pinned, bool Quiet);

/// <summary>
/// A value of a list that is data (the sheets of a workbook, the regions of the registry, the
/// settlements found by a name): a line that shows the choice and opens the list under itself, with
/// a search over a long one. Never a drop-down of the system - the list is a flyout drawn inside the
/// window, and a picture of the window shows it too. The list is read when it opens: it is what
/// the engine holds now.
/// </summary>
public sealed class PickLine
{
    readonly Func<IReadOnlyList<PickItem>> _items;
    readonly Func<string> _current;
    readonly Action<string> _choose;
    readonly TextBlock _caption = new() { VerticalAlignment = VerticalAlignment.Center, TextTrimming = TextTrimming.CharacterEllipsis };

    public Button Button { get; }

    /// <param name="items">The lines of the list now.</param>
    /// <param name="current">The key chosen now.</param>
    /// <param name="choose">What a choice does.</param>
    /// <param name="searchFrom">A search box stands over a list this long.</param>
    public PickLine(Func<IReadOnlyList<PickItem>> items, Func<string> current, Action<string> choose, int searchFrom = 9, double minWidth = 220, double maxWidth = 460)
    {
        _items = items;
        _current = current;
        _choose = choose;
        var face = new Grid { ColumnDefinitions = new ColumnDefinitions("*,Auto") };
        face.Children.Add(_caption);
        var arrow = Icons.Sign("chevron-down");
        Grid.SetColumn(arrow, 1);
        face.Children.Add(arrow);
        Button = new Button
        {
            Classes = { "pickline" }, Content = face, MinWidth = minWidth, MaxWidth = maxWidth,
            HorizontalAlignment = HorizontalAlignment.Stretch, HorizontalContentAlignment = HorizontalAlignment.Stretch,
        };

        var flyout = new Flyout { Placement = PlacementMode.BottomEdgeAlignedLeft };
        Button.Flyout = flyout;
        flyout.Opening += (_, _) =>
        {
            var rows = new StackPanel();
            var search = new TextBox { Classes = { "field" }, PlaceholderText = Lang.T("Найти: часть названия"), Margin = new Thickness(0, 0, 0, 6) };
            var all = _items().ToList();
            void Fill()
            {
                rows.Children.Clear();
                var typed = (search.Text ?? "").Trim();
                var current = _current();
                foreach (var item in all.Where(item => typed.Length == 0 || item.Name.Contains(typed, StringComparison.CurrentCultureIgnoreCase)))
                {
                    var face = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 7 };
                    // A pinned line carries its pin: the ones the person keeps at hand stand first.
                    var pin = Icons.Sign("pin");
                    pin.Opacity = item.Pinned ? 1 : 0;
                    if (item.Pinned) pin.Classes.Add("amber");
                    face.Children.Add(pin);
                    face.Children.Add(new TextBlock { Text = item.Name, TextTrimming = TextTrimming.CharacterEllipsis });
                    var row = new Button { Classes = { "histrow" }, Content = face };
                    row.Classes.Set("current", item.Key == current);
                    row.Classes.Set("gone", item.Quiet);
                    if (item.Tip.Length > 0) ToolTip.SetTip(row, item.Tip);
                    var key = item.Key;
                    row.Click += (_, _) => { flyout.Hide(); _choose(key); };
                    rows.Children.Add(row);
                }
                if (all.Count == 0) rows.Children.Add(new TextBlock { Classes = { "note" }, Text = Lang.T("список пуст"), Margin = new Thickness(8, 4), TextWrapping = TextWrapping.Wrap, MaxWidth = 420 });
            }
            search.TextChanged += (_, _) => Fill();
            search.IsVisible = all.Count > searchFrom;
            Fill();
            flyout.Content = new StackPanel
            {
                Width = Math.Max(360, Button.Bounds.Width),
                Children = { search, new ScrollViewer { MaxHeight = 360, HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled, Content = rows } },
            };
            if (search.IsVisible) Avalonia.Threading.Dispatcher.UIThread.Post(() => search.Focus(), Avalonia.Threading.DispatcherPriority.Background);
        };
        Repaint();
    }

    /// <summary>The caption of the line: the name of the key chosen, or what stands for "nothing".</summary>
    public void Repaint(bool loading = false, string error = "")
    {
        var value = _current();
        var items = _items();
        var known = items.FirstOrDefault(item => item.Key == value);
        _caption.Text = loading ? Lang.T("читаю…")
            : known is not null ? known.Name
            : value.Length > 0 ? value
            : error.Length > 0 ? Lang.F("не прочитать: {0}", error)
            : items.FirstOrDefault(item => item.Key.Length == 0)?.Name is { Length: > 0 } empty ? empty : Lang.T("не выбрано");
        _caption.Classes.Set("quiet", loading || value.Length == 0);
        if (error.Length > 0) ToolTip.SetTip(Button, Lang.F("не прочитать: {0}", error));
    }
}
