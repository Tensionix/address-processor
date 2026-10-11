using System;
using System.IO;
using Avalonia;

namespace AudionAddressProcessor;

class Program
{
    /// <summary>
    /// --self-check or --self-check=FILE: the window builds every section of the manifest without
    /// being shown, writes what it built into the file and exits with a code (MainWindow.Check.cs).
    /// Null - an ordinary start.
    /// </summary>
    public static string? SelfCheckFile { get; private set; }

    [System.Runtime.InteropServices.DllImport("shell32.dll", CharSet = System.Runtime.InteropServices.CharSet.Unicode)]
    static extern int SetCurrentProcessExplicitAppUserModelID(string appId);

    // Initialization code. Don't use any Avalonia, third-party APIs or any
    // SynchronizationContext-reliant code before AppMain is called: things aren't initialized
    // yet and stuff might break.
    [STAThread]
    public static int Main(string[] args)
    {
        // Before anything that can fail: an end of the program at its very start leaves logs\gui-crash-*.log too.
        Core.CrashGuard.Early();
        // The name the taskbar groups the windows of this program by - the one Start.exe has, so the two are one button.
        try { SetCurrentProcessExplicitAppUserModelID("Audion.Tools.Audion.Address.Processor"); } catch { }
        // --root "<folder>" - the project of this start, named the way the door takes it. Without
        // it the project is the folder the window stands in.
        for (int i = 0; i < args.Length; i++)
        {
            var arg = args[i];
            if (string.Equals(arg, "--self-check", StringComparison.OrdinalIgnoreCase)) SelfCheckFile = "";
            else if (arg.StartsWith("--self-check=", StringComparison.OrdinalIgnoreCase)) SelfCheckFile = arg[(arg.IndexOf('=') + 1)..].Trim().Trim('"');

            string? named = null;
            if (string.Equals(arg, "-Root", StringComparison.OrdinalIgnoreCase) || string.Equals(arg, "--root", StringComparison.OrdinalIgnoreCase))
                named = i + 1 < args.Length ? args[i + 1] : "";
            else if (arg.StartsWith("--root=", StringComparison.OrdinalIgnoreCase) || arg.StartsWith("-Root:", StringComparison.OrdinalIgnoreCase))
                named = arg[(arg.IndexOfAny(new[] { '=', ':' }) + 1)..];
            if (named is not null) Core.Paths.Use(named.Trim().Trim('"'));
        }
        if (SelfCheckFile is { Length: 0 }) SelfCheckFile = Path.Combine(Core.Paths.Logs, "gui-self-check.json");

        // One window per project folder: a second start brings the first one forward and leaves.
        // A check (a Debug build, the self-check) is not held back by the window the owner works in.
#if !DEBUG
        bool claimed = false;
        if (SelfCheckFile is null)
        {
            if (!Core.OneWindow.Claim("AudionAddressProcessor")) return 0;
            claimed = true;
        }
#endif
        int code = BuildAvaloniaApp().StartWithClassicDesktopLifetime(args);
#if !DEBUG
        GC.KeepAlive(claimed);
#endif
        return code;
    }

    // Avalonia configuration, don't remove; also used by visual designer.
    public static AppBuilder BuildAvaloniaApp()
        => AppBuilder.Configure<App>()
            .UsePlatformDetect()
            .WithInterFont()
            // JetBrains Mono (SIL OFL, Assets\Fonts\JetBrainsMono) ships inside the program like Inter:
            // the font of the window and of the journal, with Cyrillic, nothing to fetch or install.
            .ConfigureFonts(fonts => fonts.AddFontCollection(new Avalonia.Media.Fonts.EmbeddedFontCollection(
                new Uri("fonts:JetBrainsMono"), new Uri("avares://AudionAddressProcessor/Assets/Fonts/JetBrainsMono"))))
            // Drop-downs and tooltips are drawn inside the window, not as separate native windows:
            // a picture of the window shows them too.
            .With(new Win32PlatformOptions { OverlayPopups = true })
            .LogToTrace();
}
