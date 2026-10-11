using Avalonia.Controls.Shapes;
using Avalonia.Media;

namespace AudionAddressProcessor;

/// <summary>
/// How the signs of Icons.cs get onto the screen. A Lucide sign is strokes on a 24 grid, shown on
/// the 10 grid of the style "Path.icon" (the shell of Audion Disk Tools: centred by App.CenterIcon,
/// the line as thick as there).
/// </summary>
public static partial class Icons
{
    /// <summary>The geometry of a Lucide sign on the 10 grid; null when the set has no such name.</summary>
    public static Geometry? Glyph(string name)
    {
        if (Made.TryGetValue(name, out var made)) return made;
        if (!Lucide.TryGetValue(name, out var data)) return null;
        var geometry = Geometry.Parse(data);
        // Scaled in the geometry, not by a Viewbox: the pen keeps the thickness of the style.
        geometry.Transform = new ScaleTransform(10 / 24.0, 10 / 24.0);
        // A sign is drawn hundreds of times on a page of cards: its drawing is read once and shared.
        return Made[name] = geometry;
    }

    static readonly System.Collections.Generic.Dictionary<string, Geometry> Made = new();

    /// <summary>A Lucide sign ready for a button.</summary>
    public static Path Sign(string name) => new() { Classes = { "icon" }, Data = Glyph(name) };
}
