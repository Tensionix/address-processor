using System;
using System.Collections.Generic;
using System.Linq;
using Avalonia;
using Avalonia.Controls;

namespace AudionAddressProcessor.Views;

/// <summary>
/// The frames of a form in columns: as many equal columns as the width holds (a frame wants a column
/// of at least <see cref="MinColumn"/>, three at most). The frames go in the order of the manifest,
/// each into the column that is the lowest at that moment, so the columns end about together and
/// no blank is left under a short frame; a frame marked wide takes a row of its own, under all
/// the columns.
/// </summary>
public sealed class GroupGrid : Panel
{
    public static readonly StyledProperty<double> MinColumnProperty = AvaloniaProperty.Register<GroupGrid, double>(nameof(MinColumn), 380);
    public static readonly StyledProperty<double> GapProperty = AvaloniaProperty.Register<GroupGrid, double>(nameof(Gap), 8);
    public static readonly AttachedProperty<bool> WideProperty = AvaloniaProperty.RegisterAttached<GroupGrid, Control, bool>("Wide");

    static GroupGrid()
    {
        AffectsMeasure<GroupGrid>(MinColumnProperty, GapProperty);
        AffectsParentMeasure<GroupGrid>(WideProperty);
    }

    public double MinColumn { get => GetValue(MinColumnProperty); set => SetValue(MinColumnProperty, value); }
    public double Gap { get => GetValue(GapProperty); set => SetValue(GapProperty, value); }
    public static bool GetWide(Control control) => control.GetValue(WideProperty);
    public static void SetWide(Control control, bool wide) => control.SetValue(WideProperty, wide);

    readonly List<(Control Child, Rect Place)> _places = new();

    protected override Size MeasureOverride(Size availableSize)
    {
        _places.Clear();
        var shown = Children.Where(child => child.IsVisible).ToList();
        double width = double.IsInfinity(availableSize.Width) ? MinColumn : availableSize.Width;
        // No more columns than frames that share them: two frames are two wide columns, not two and a blank.
        int sharing = Math.Max(1, shown.Count(child => !GetWide(child)));
        int columns = Math.Clamp((int)Math.Floor((width + Gap) / (MinColumn + Gap)), 1, Math.Min(3, sharing));
        double column = (width - Gap * (columns - 1)) / columns;

        var heights = new double[columns];
        foreach (var child in shown)
        {
            if (GetWide(child) || columns == 1)
            {
                child.Measure(new Size(width, double.PositiveInfinity));
                double top = heights.Max();
                _places.Add((child, new Rect(0, top, width, child.DesiredSize.Height)));
                Array.Fill(heights, top + child.DesiredSize.Height + Gap);
                continue;
            }
            int at = 0;
            for (int i = 1; i < columns; i++) if (heights[i] < heights[at] - 0.5) at = i;
            child.Measure(new Size(column, double.PositiveInfinity));
            _places.Add((child, new Rect(at * (column + Gap), heights[at], column, child.DesiredSize.Height)));
            heights[at] += child.DesiredSize.Height + Gap;
        }
        return new Size(width, Math.Max(0, heights.Max() - Gap));
    }

    protected override Size ArrangeOverride(Size finalSize)
    {
        foreach (var (child, place) in _places) child.Arrange(place);
        return finalSize;
    }
}

/// <summary>
/// Flags (or chips) in columns of equal width: as many columns as the width holds for the longest
/// of them - a name is never cut to make a column fit - up to <see cref="MaxColumns"/>. The flags
/// stand row by row in the order of the manifest, so a person reads them as a table.
/// </summary>
public sealed class FlagGrid : Panel
{
    public static readonly StyledProperty<int> MaxColumnsProperty = AvaloniaProperty.Register<FlagGrid, int>(nameof(MaxColumns), 4);
    public static readonly StyledProperty<double> ColumnGapProperty = AvaloniaProperty.Register<FlagGrid, double>(nameof(ColumnGap), 6);
    public static readonly StyledProperty<double> RowGapProperty = AvaloniaProperty.Register<FlagGrid, double>(nameof(RowGap), 4);
    public static readonly StyledProperty<bool> StretchProperty = AvaloniaProperty.Register<FlagGrid, bool>(nameof(Stretch), true);

    static FlagGrid()
    {
        AffectsMeasure<FlagGrid>(MaxColumnsProperty, ColumnGapProperty, RowGapProperty, StretchProperty);
    }

    public int MaxColumns { get => GetValue(MaxColumnsProperty); set => SetValue(MaxColumnsProperty, value); }
    public double ColumnGap { get => GetValue(ColumnGapProperty); set => SetValue(ColumnGapProperty, value); }
    public double RowGap { get => GetValue(RowGapProperty); set => SetValue(RowGapProperty, value); }

    /// <summary>The columns share the whole width (true), or each is as wide as the longest flag and they stand to the left (false).</summary>
    public bool Stretch { get => GetValue(StretchProperty); set => SetValue(StretchProperty, value); }

    readonly List<(Control Child, Rect Place)> _places = new();

    protected override Size MeasureOverride(Size availableSize)
    {
        _places.Clear();
        var shown = Children.Where(child => child.IsVisible).ToList();
        if (shown.Count == 0) return default;
        double widest = 0;
        foreach (var child in shown)
        {
            child.Measure(new Size(double.PositiveInfinity, double.PositiveInfinity));
            widest = Math.Max(widest, child.DesiredSize.Width);
        }
        double width = double.IsInfinity(availableSize.Width) ? widest : availableSize.Width;
        int columns = Math.Clamp((int)Math.Floor((width + ColumnGap) / (widest + ColumnGap)), 1, Math.Min(MaxColumns, shown.Count));
        double column = Stretch ? (width - ColumnGap * (columns - 1)) / columns : widest;
        double y = 0;
        for (int start = 0; start < shown.Count; start += columns)
        {
            var row = shown.Skip(start).Take(columns).ToList();
            double height = 0;
            foreach (var child in row)
            {
                child.Measure(new Size(column, double.PositiveInfinity));
                height = Math.Max(height, child.DesiredSize.Height);
            }
            for (int i = 0; i < row.Count; i++) _places.Add((row[i], new Rect(i * (column + ColumnGap), y, column, height)));
            y += height + RowGap;
        }
        return new Size(width, Math.Max(0, y - RowGap));
    }

    protected override Size ArrangeOverride(Size finalSize)
    {
        foreach (var (child, place) in _places) child.Arrange(place);
        return finalSize;
    }
}
