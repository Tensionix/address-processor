using System;
using System.Linq;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.ApplicationLifetimes;
using Avalonia.Markup.Xaml;
using Avalonia.Media;
using Avalonia.Styling;
using Avalonia.VisualTree;

namespace AudionAddressProcessor;

/// <summary>
/// The shell of Audion Sync Tools (and through it of Audion Disk Tools): the themes, the sizes
/// and the styles of App.axaml, the tooltips and the icons. What those programs paint for their
/// file lists alone - grain, glass, zebra - is switched off here by plain values of the same
/// resources.
/// </summary>
public partial class App : Application
{
    // Normal-step sizes; a step adds the same amount to every one of them.
    static readonly (string Key, double Normal)[] FontSizes =
    {
        ("FontBase", 13), ("FontPanel", 12), ("FontHeader", 11), ("FontButton", 10),
        ("FontHint", 8.5), ("FontSwitch", 10.5), ("FontCaption", 10.5), ("FontCrumb", 11),
        // The journal: a point smaller than a panel - it holds long lines.
        ("FontLog", 10.5),
        // The numbers of the last run.
        ("FontCount", 17),
        // The scale of the window's own texts (written out at the end of the styles of App.axaml).
        ("FontTitle", 14), ("FontBlock", 12.5), ("FontTip", 12), ("FontCard", 11.5), ("FontField", 10.5), ("FontFine", 9.5), ("FontBadge", 9),
    };

    public override void Initialize()
    {
        AvaloniaXamlLoader.Load(this);
        // Tooltips come after 1500 ms, as in every Audion program, and the neighbour gets no quick
        // show: moving along a row of buttons must not pop them all.
        ToolTip.TipProperty.Changed.AddClassHandler<Control>((control, _) =>
        {
            control.SetValue(ToolTip.ShowDelayProperty, 1500);
            control.SetValue(ToolTip.BetweenShowDelayProperty, 0);
        });
        // No icon is drawn by hand: the markup names a sign of the owner's sets (Tag="play") and gets
        // its geometry here, from Icons.cs. Then every icon, now and later, is centred and scaled the same way.
        Control.LoadedEvent.AddClassHandler<Avalonia.Controls.Shapes.Path>((path, _) =>
        {
            if (path.Data is null && path.Tag is string name && path.Classes.Contains("icon") && Icons.Glyph(name) is { } sign) path.Data = sign;
            CenterIcon(path);
            if (path.Classes.Contains("icon") && !Settled.TryGetValue(path, out var known))
            {
                Settled.Add(path, new Place());
                path.LayoutUpdated += (_, _) => SettleIcon(path);
            }
        });
        Avalonia.Controls.Shapes.Path.DataProperty.Changed.AddClassHandler<Avalonia.Controls.Shapes.Path>((path, _) => CenterIcon(path));
        // The mark of the chosen line of a menu is tangerine, as in Disk Tools and Sync Tools.
        Control.LoadedEvent.AddClassHandler<Avalonia.Controls.Shapes.Ellipse>((dot, _) =>
        {
            if (dot.Parent is ContentControl { Name: "PART_ToggleIconPresenter" } && Current?.TryGetResource("Tangerine", Current.ActualThemeVariant, out var ink) == true && ink is IBrush brush)
                dot.Fill = brush;
        });
    }

    /// <summary>How much larger than its 10 grid an icon is shown.</summary>
    const double IconScale = 1.26;

    /// <summary>
    /// An icon drawn off the middle of its 10 box is moved by the exact bounds of its drawing to
    /// the middle, then scaled around it.
    /// </summary>
    static void CenterIcon(Avalonia.Controls.Shapes.Path path)
    {
        if (!path.Classes.Contains("icon") || path.Data is not { } data) return;
        var bounds = data.Bounds;
        var dx = 5 - (bounds.X + bounds.Width / 2);
        var dy = 5 - (bounds.Y + bounds.Height / 2);
        path.RenderTransformOrigin = new RelativePoint(0.5, 0.5, RelativeUnit.Relative);
        // The third step is the half pixel the layout could not give (SettleIcon); it outlives a new drawing.
        var settle = path.RenderTransform is TransformGroup { Children.Count: 3 } old ? old.Children[2] : new TranslateTransform();
        path.RenderTransform = new TransformGroup
        {
            Children = { new TranslateTransform(dx, dy), new ScaleTransform(IconScale, IconScale), settle },
        };
    }

    sealed class Place { public string At = ""; }

    static readonly System.Runtime.CompilerServices.ConditionalWeakTable<Avalonia.Controls.Shapes.Path, Place> Settled = new();

    /// <summary>
    /// A button that holds an icon alone has it in its very middle, on the pixels of the screen.
    /// The layout puts the box of an icon on a whole pixel: at 150% a button is 36 pixels and the
    /// box 15, so the box stood half a pixel to the left and up. The half pixel is given back as a
    /// render offset; nothing is a constant - the sizes and the scale are read as they are.
    /// </summary>
    static void SettleIcon(Avalonia.Controls.Shapes.Path path)
    {
        if (!Settled.TryGetValue(path, out var place) || path.RenderTransform is not TransformGroup { Children.Count: 3 } group
            || group.Children[2] is not TranslateTransform settle || !path.IsEffectivelyVisible) return;
        if (path.FindAncestorOfType<Button>() is not { } host || TopLevel.GetTopLevel(path) is not { } top) return;
        double scale = top.RenderScaling, x = 0, y = 0;
        for (Visual? v = path; v != null && v != host; v = v.GetVisualParent()) { x += v.Bounds.X; y += v.Bounds.Y; }
        var key = $"{scale}|{host.Bounds.Size}|{x}|{y}|{path.Bounds.Size}";
        if (key == place.At) return;
        place.At = key;
        // An icon beside a word keeps the place the layout gave it: the word is its neighbour, not the button.
        bool alone = !host.GetVisualDescendants().OfType<TextBlock>().Any(text => text.IsVisible && !string.IsNullOrEmpty(text.Text));
        settle.X = alone ? host.Bounds.Width / 2 - (x + path.Bounds.Width / 2) : 0;
        settle.Y = alone ? host.Bounds.Height / 2 - (y + path.Bounds.Height / 2) : 0;
    }

    // ---- the rims of the controls

    /// <summary>
    /// How much of its strength the rim of a control keeps: it is dimmed by 70%. The owner, 11.10.2026:
    /// «Глушим окантовки контролов на 70%» - many rims side by side flicker. A rim coloured from the code
    /// takes the same share (<see cref="Rim(Color, double)"/>).
    /// </summary>
    public const double RimKeeps = 0.3;

    /// <summary>
    /// The brushes a rim of a control is made of, by their keys in the themes of App.axaml: of a button and of a
    /// field, under the pointer and of a switch that is on, of the buttons that run, warn and remove, of a switch
    /// at rest, of a pinned tab, of a check box that is off and on. Panels, cards, frames, badges and separators
    /// are not controls: they keep the brushes themselves.
    /// </summary>
    static readonly string[] Rims = { "BorderSoft", "Quasar", "RunBorder", "WarnBorder", "AmberBorder", "AmberInk", "DangerBorder", "SwitchBorder", "PinBorder", "TextMuted", "TextMain" };

    /// <summary>
    /// For each brush of a rim, one that keeps a part of its strength, under the same key with "Rim" after it:
    /// made anew for the theme in use, so no colour is written twice and every theme has its own. The styles of
    /// App.axaml and Window.Styles.axaml that frame a control ask for them.
    /// </summary>
    public static void DimRims()
    {
        if (Current is not { } app) return;
        foreach (var key in Rims)
            if (app.TryGetResource(key, app.ActualThemeVariant, out var value) && value is ISolidColorBrush brush)
                app.Resources[key + "Rim"] = new SolidColorBrush(brush.Color, brush.Opacity * RimKeeps);
    }

    /// <summary>The rim of a control in a colour the code chose: the same share of its strength.</summary>
    public static IBrush Rim(Color colour, double opacity = 1) => new SolidColorBrush(colour, opacity * RimKeeps);

    public override void OnFrameworkInitializationCompleted()
    {
        Resources["Grain"] = Brushes.Transparent;
        Resources["Zebra"] = Brushes.Transparent;
        Resources["ListOpacity"] = 1.0;
        if (ApplicationLifetime is IClassicDesktopStyleApplicationLifetime desktop)
        {
            // Before the window: an error in its own constructor is written down too.
            Core.CrashGuard.Install();
            var settings = Core.Settings.Load();
            Core.Lang.Set(settings.LanguageInUse);
            RequestedThemeVariant = Variant(settings.Look);
            DimRims();
            ActualThemeVariantChanged += (_, _) => DimRims();
            if (Program.SelfCheckFile is { } file)
            {
                // The self-check: the window is made and builds everything, but is never shown.
                desktop.ShutdownMode = ShutdownMode.OnExplicitShutdown;
                var hidden = new MainWindow(settings);
                Avalonia.Threading.Dispatcher.UIThread.Post(async () => desktop.Shutdown(await hidden.SelfCheck(file)));
                base.OnFrameworkInitializationCompleted();
                return;
            }
            desktop.MainWindow = new MainWindow(settings);
        }
        base.OnFrameworkInitializationCompleted();
    }

    /// <summary>-1 smaller, 0 normal, +1 larger.</summary>
    public static void SetFontStep(int step)
    {
        if (Current is null) return;
        double add = step switch { < 0 => -1, > 0 => 1.5, _ => 0 };
        foreach (var (key, normal) in FontSizes) Current.Resources[key] = normal + add;
    }

    /// <summary>Audion Code Dark: the "CodeDark" dictionary of App.axaml, the rest from Dark.</summary>
    public static ThemeVariant CodeDark { get; } = new("CodeDark", ThemeVariant.Dark);

    /// <summary>Audion Vault Dark: the "VaultDark" dictionary of App.axaml, the rest from Dark.</summary>
    public static ThemeVariant VaultDark { get; } = new("VaultDark", ThemeVariant.Dark);

    /// <summary>The variant of a theme of the settings: "dark", "codedark", "vault", "light".</summary>
    public static ThemeVariant Variant(string theme) => theme switch
    {
        "light" => ThemeVariant.Light, "codedark" => CodeDark, "vault" => VaultDark, _ => ThemeVariant.Dark,
    };

    /// <summary>A brush of the current theme by its key; a neutral grey when the key is unknown.</summary>
    public static IBrush Ink(string key) =>
        Current is { } app && app.TryGetResource(key, app.ActualThemeVariant, out var value) && value is IBrush brush ? brush : Brushes.Gray;
}
