using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Input;
using Avalonia.Layout;
using Avalonia.Media;
using Avalonia.VisualTree;
using AudionAddressProcessor.Core;
using Shapes = Avalonia.Controls.Shapes;

namespace AudionAddressProcessor.Views;

/// <summary>
/// The line of the address (`enabled_slots`, `slot_order`, `slot_preview` of the manifest, the same
/// three fields in the collection, the normalisation and the processing of the reference): which
/// slots an address is written with and in what order. One control instead of three fields: the
/// address as it will be written on top, under it a chip for each slot of the hierarchy - its tick
/// and its place, moved by a drag - and the technical keys the engine adds apart, ticks only.
///
/// The values are those of the three fields, nothing else is kept: `slot_order` is the object
/// "slot: place" as before, `enabled_slots` the list of the ticked ones.
/// </summary>
public sealed partial class Form
{
    Control SlotLadder(Field? preview, Field enabled, Field order)
    {
        var slots = _manifest()?.Slots ?? new SlotInfo();
        var ordered = order.Options.Select(option => option.Key).Where(key => key.Length > 0).ToList();
        var technical = enabled.Options.Where(option => !option.Header && !ordered.Contains(option.Key)).ToList();
        var byKey = enabled.Options.ToDictionary(option => option.Key, option => option);

        var host = new StackPanel();

        // The head: the name, and the way back to the defaults of the manifest.
        var head = new Grid { ColumnDefinitions = new ColumnDefinitions("Auto,Auto,*,Auto"), Margin = new Thickness(0, 0, 0, 6), MinHeight = 24 };
        var name = new TextBlock { Classes = { "flabel" }, Text = Lang.T("Линейка адреса") };
        ToolTip.SetTip(name, Lang.T("Из каких частей собирается адрес и в каком порядке. Часть включается галочкой; порядок меняется перетаскиванием."));
        head.Children.Add(name);
        var mark = Mark(order);
        Grid.SetColumn(mark, 1);
        head.Children.Add(mark);
        var reset = new Button { Classes = { "tool", "io" }, Content = Icons.Sign("undo-2") };
        ToolTip.SetTip(reset, Lang.T("К умолчаниям: включённые части и порядок, как в манифесте."));
        reset.Click += (_, _) => _values.Reset(new[] { enabled, order });
        Grid.SetColumn(reset, 3);
        head.Children.Add(reset);
        host.Children.Add(head);

        // The address as it will be written, by the samples of the engine.
        var line = new TextBlock { Classes = { "slotpreview" }, TextWrapping = TextWrapping.Wrap };
        host.Children.Add(new Border { Classes = { "slotline" }, Child = line });

        // The hierarchy: one chip for each slot, in the order of their places.
        var chips = new FlagGrid { MaxColumns = 7 };
        var chipOf = new Dictionary<string, Border>();
        foreach (var slot in ordered)
            chipOf[slot] = Chip(slot, byKey.TryGetValue(slot, out var option) ? option : new Option(), slots, chips);
        host.Children.Add(chips);

        // The keys the engine adds apart (codes, the base of a house, the key of the match): a tick each.
        var keys = new FlagGrid { MaxColumns = 6 };
        var keyFlags = new List<(Avalonia.Controls.Primitives.ToggleButton Flag, string Key)>();
        foreach (var option in technical)
        {
            var flag = Tick(slots.Short(option.Key) is { } nameOfKey && nameOfKey != option.Key ? nameOfKey : option.Caption);
            flag.HorizontalAlignment = HorizontalAlignment.Stretch;
            flag.HorizontalContentAlignment = HorizontalAlignment.Left;
            var tip = option.Tip.Length > 0 ? option.Tip : option.Name;
            if (tip.Length > 0) ToolTip.SetTip(flag, tip);
            var key = option.Key;
            flag.Click += (_, _) => Toggle(key, flag.IsChecked == true);
            keyFlags.Add((flag, key));
            keys.Children.Add(flag);
        }
        if (keyFlags.Count > 0)
        {
            host.Children.Add(new TextBlock { Classes = { "flabel" }, Text = Lang.T("Технические ключи"), Margin = new Thickness(0, 6, 0, 4) });
            host.Children.Add(keys);
        }

        void Toggle(string slot, bool on)
        {
            var now = _values.Picked(enabled);
            if (on) now.Add(slot); else now.Remove(slot);
            _values.Set(enabled, string.Join(Values.ListSeparator, enabled.Options.Select(item => item.Key).Where(now.Contains)));
        }

        Dictionary<string, int> Places()
        {
            var places = new Dictionary<string, int>();
            try
            {
                using var doc = JsonDocument.Parse(_values.Get(order));
                if (doc.RootElement.ValueKind == JsonValueKind.Object)
                    foreach (var property in doc.RootElement.EnumerateObject())
                        if (property.Value.TryGetInt32(out var place)) places[property.Name] = place;
            }
            catch { }
            return places;
        }

        void Paint()
        {
            var places = Places();
            var picked = _values.Picked(enabled);
            // The chips stand in the order of their places; a chip being dragged stands where the hand put it.
            if (chips.Children.OfType<Border>().All(chip => !chip.Classes.Contains("dragging")))
            {
                var sequence = ordered.Select((slot, index) => (slot, index)).OrderBy(item => places.TryGetValue(item.slot, out var place) ? place : 999).ThenBy(item => item.index).Select(item => item.slot).ToList();
                if (!chips.Children.OfType<Border>().Select(chip => (string)chip.Tag!).SequenceEqual(sequence))
                {
                    chips.Children.Clear();
                    foreach (var slot in sequence) chips.Children.Add(chipOf[slot]);
                }
            }
            int shown = 0;
            foreach (var chip in chips.Children.OfType<Border>())
            {
                var slot = (string)chip.Tag!;
                bool on = picked.Contains(slot);
                chip.Classes.Set("off", !on);
                var parts = ((Grid)chip.Child!).Children;
                if (parts[0] is StackPanel left && left.Children[0] is Avalonia.Controls.Button tick && tick.Content is Border box) box.Classes.Set("on", on);
                if (parts[^1] is TextBlock place) place.Text = on ? (++shown).ToString() : "–";
            }
            foreach (var (flag, key) in keyFlags) flag.IsChecked = picked.Contains(key);
            line.Text = SlotPreview(slots, picked, places, preview);
        }
        Watch(enabled, Paint);
        Watch(order, Paint);
        return host;
    }

    /// <summary>The address as the slots would write it: the enabled ones that have a sample, in the order of their places.</summary>
    static string SlotPreview(SlotInfo slots, HashSet<string> picked, Dictionary<string, int> places, Field? preview)
    {
        var keys = slots.Samples.Keys.Where(picked.Contains).ToList();
        if (slots.Samples.Count == 0) return preview is null ? "" : Values.DefaultOf(preview);
        keys = keys.Select((key, index) => (key, index)).OrderBy(item => places.TryGetValue(item.key, out var place) && place > 0 ? place : 999).ThenBy(item => item.index).Select(item => item.key).ToList();
        return string.Join(" · ", keys.Select(key => slots.Samples[key]));
    }

    /// <summary>
    /// A chip of the hierarchy: the tick, the name, the place among the ticked ones. The tick is a
    /// button of its own; anywhere else the chip is taken by the hand and moved - the others make way
    /// as it passes, and the places are written when it is let go.
    /// </summary>
    Border Chip(string slot, Option option, SlotInfo slots, Panel panel)
    {
        var name = slots.Short(slot) is { } known && known != slot ? known : option.Caption;
        var order = _node?.Fields.FirstOrDefault(field => field.Kind == "slot_order");
        var enabled = _node?.Fields.FirstOrDefault(field => field.Kind == "checkboxes" && field.Id == "enabled_slots");

        var box = new Border
        {
            Classes = { "tickbox" },
            Child = new Shapes.Path { Classes = { "tick" }, Data = Geometry.Parse("M 1.5,5 L 4,7.5 L 8.5,2.5") },
        };
        var tick = new Button { Classes = { "slottick" }, Content = box };
        var label = new TextBlock { Text = name, VerticalAlignment = VerticalAlignment.Center };
        var place = new TextBlock { Classes = { "slotnum" }, VerticalAlignment = VerticalAlignment.Center };
        var left = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 6, Margin = new Thickness(4, 0, 8, 0), VerticalAlignment = VerticalAlignment.Center, Children = { tick, label } };
        var rule = new Border { Classes = { "slotsep" } };
        var face = new Grid { ColumnDefinitions = new ColumnDefinitions("*,Auto,Auto") };
        Grid.SetColumn(rule, 1);
        Grid.SetColumn(place, 2);
        face.Children.Add(left);
        face.Children.Add(rule);
        face.Children.Add(place);
        var chip = new Border { Classes = { "slotchip" }, Child = face, Tag = slot, Cursor = new Cursor(StandardCursorType.SizeAll) };
        var tip = option.Tip.Length > 0 ? option.Tip : option.Name;
        ToolTip.SetTip(chip, (tip.Length > 0 ? tip + "\n" : "") + Lang.T("Перетащите, чтобы поменять порядок."));

        tick.Click += (_, _) =>
        {
            if (enabled is null) return;
            var now = _values.Picked(enabled);
            if (!now.Remove(slot)) now.Add(slot);
            _values.Set(enabled, string.Join(Values.ListSeparator, enabled.Options.Select(item => item.Key).Where(now.Contains)));
        };

        Point start = default;
        bool held = false, dragging = false;
        chip.PointerPressed += (_, e) =>
        {
            if (!e.GetCurrentPoint(chip).Properties.IsLeftButtonPressed) return;
            held = true;
            dragging = false;
            start = e.GetPosition(panel);
            e.Pointer.Capture(chip);
            e.Handled = true;
        };
        chip.PointerMoved += (_, e) =>
        {
            if (!held) return;
            var at = e.GetPosition(panel);
            if (!dragging)
            {
                if (Math.Abs(at.X - start.X) + Math.Abs(at.Y - start.Y) < 6) return;
                dragging = true;
                chip.Classes.Add("dragging");
            }
            // The chip under the hand: the dragged one takes its place in the row.
            if (panel.InputHitTest(at) is Visual hit)
            {
                Visual? target = hit;
                while (target is not null && target.GetVisualParent() != panel) target = target.GetVisualParent();
                if (target is Border other && other != chip && other.Tag is string)
                {
                    int to = panel.Children.IndexOf(other);
                    if (to >= 0)
                    {
                        panel.Children.Remove(chip);
                        panel.Children.Insert(Math.Min(to, panel.Children.Count), chip);
                    }
                }
            }
            e.Handled = true;
        };
        // Let go - by the hand, or by the system taking the pointer away (Alt+Tab, a window that pops up).
        bool Drop()
        {
            if (!held) return false;
            held = false;
            if (!dragging) return false;
            dragging = false;
            chip.Classes.Remove("dragging");
            if (order is null) return false;
            // The places are written as the chips stand: 1 to the number of the slots.
            var places = new System.Text.StringBuilder("{");
            int number = 0;
            foreach (var other in panel.Children.OfType<Border>())
                places.Append(number++ == 0 ? "" : ",").Append(JsonSerializer.Serialize((string)other.Tag!)).Append(':').Append(number);
            places.Append('}');
            _values.Set(order, places.ToString());
            return true;
        }
        chip.PointerReleased += (_, e) =>
        {
            if (!held) return;
            e.Pointer.Capture(null);
            if (Drop()) e.Handled = true;
        };
        chip.PointerCaptureLost += (_, _) => Drop();
        return chip;
    }
}
