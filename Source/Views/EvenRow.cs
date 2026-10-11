using System;
using System.Linq;
using Avalonia;
using Avalonia.Controls;

namespace AudionAddressProcessor.Views;

/// <summary>
/// A row of switches that share its width equally - until a name does not fit its share: that
/// switch takes the width of its name, and the others share what is left. A band of four pages
/// stands as the sections over it do; a fifth page must not cut the name of its neighbour.
/// </summary>
public sealed class EvenRow : Panel
{
    public static readonly StyledProperty<double> SpacingProperty = AvaloniaProperty.Register<EvenRow, double>(nameof(Spacing));

    static EvenRow()
    {
        AffectsMeasure<EvenRow>(SpacingProperty);
    }

    public double Spacing
    {
        get => GetValue(SpacingProperty);
        set => SetValue(SpacingProperty, value);
    }

    protected override Size MeasureOverride(Size availableSize)
    {
        double wanted = 0, height = 0;
        int shown = 0;
        foreach (var child in Children)
        {
            if (!child.IsVisible) continue;
            child.Measure(new Size(double.PositiveInfinity, availableSize.Height));
            wanted += child.DesiredSize.Width;
            height = Math.Max(height, child.DesiredSize.Height);
            shown++;
        }
        wanted += Spacing * Math.Max(0, shown - 1);
        return new Size(double.IsInfinity(availableSize.Width) ? wanted : availableSize.Width, height);
    }

    protected override Size ArrangeOverride(Size finalSize)
    {
        var shown = Children.Where(child => child.IsVisible).ToList();
        if (shown.Count == 0) return finalSize;
        var widths = Shares(shown.Select(child => child.DesiredSize.Width).ToArray(), finalSize.Width - Spacing * (shown.Count - 1));
        double left = 0;
        for (int i = 0; i < shown.Count; i++)
        {
            shown[i].Arrange(new Rect(left, 0, widths[i], finalSize.Height));
            left += widths[i] + Spacing;
        }
        return finalSize;
    }

    /// <summary>
    /// Equal shares of the room; whoever wants more than a share is given what it wants, and the
    /// rest share what is left - again and again, until every share fits its owner.
    /// </summary>
    public static double[] Shares(double[] wants, double room)
    {
        var widths = new double[wants.Length];
        var settled = new bool[wants.Length];
        while (true)
        {
            int free = settled.Count(one => !one);
            if (free == 0) break;
            double share = Math.Max(0, (room - Enumerable.Range(0, wants.Length).Where(i => settled[i]).Sum(i => widths[i])) / free);
            bool grew = false;
            for (int i = 0; i < wants.Length; i++)
                if (!settled[i] && wants[i] > share) { settled[i] = true; widths[i] = wants[i]; grew = true; }
            if (grew) continue;
            for (int i = 0; i < wants.Length; i++)
                if (!settled[i]) widths[i] = share;
            break;
        }
        return widths;
    }
}
