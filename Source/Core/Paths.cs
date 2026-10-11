using System;
using System.Diagnostics;
using System.IO;

namespace AudionAddressProcessor.Core;

/// <summary>
/// Where things live in the project:
///   Start.exe                 the launcher at the root
///   App\                      the window and its read-only data (config\i18n.json)
///   address_cli.cmd           the console command of the engine: what every button of the window runs
///   system_core\, runtime\    the engine (Python) - the business of the door, not of the window
///   config\                   tool_manifest.yaml and the standards (the engine's), version.json,
///                             path_history.json (shared with the window before this one), window_settings.json (the window's own)
///   input\, output\           the working folders the window starts with
///   logs\, report\            the journal of every operation and its reports; the journal of the window
/// </summary>
public static class Paths
{
    /// <summary>The program folder: binaries and the data that ships with them.</summary>
    public static string App { get; } = AppContext.BaseDirectory.TrimEnd('\\', '/');

    /// <summary>The name of the door the window is the face of.</summary>
    public const string DoorName = "address_cli.cmd";

    /// <summary>
    /// The project root: the folder that holds the console door, found by walking up from the
    /// program - one level from App\, several from Source\bin\Debug\net10.0. A root named on the
    /// command line (--root) replaces it for this start.
    /// </summary>
    public static string Root { get; private set; } = FindRoot();

    /// <summary>The project of this start, named on the command line.</summary>
    public static void Use(string root)
    {
        try { if (Directory.Exists(root)) Root = Path.GetFullPath(root).TrimEnd('\\', '/'); } catch { }
    }

    /// <summary>Started from App\ under the root: the released layout, not a build run from bin\.</summary>
    public static bool Released =>
        string.Equals(Path.GetDirectoryName(App), Root, StringComparison.OrdinalIgnoreCase) &&
        string.Equals(Path.GetFileName(App), "App", StringComparison.OrdinalIgnoreCase);

    static string FindRoot()
    {
        for (var dir = new DirectoryInfo(App); dir is not null; dir = dir.Parent)
            if (File.Exists(Path.Combine(dir.FullName, DoorName))) return dir.FullName;
        return App;
    }

    /// <summary>The console door of the engine.</summary>
    public static string Door => Path.Combine(Root, DoorName);

    /// <summary>
    /// The Python of the project, looked for where the door looks for it; "" when the environment
    /// has not been built yet.
    /// </summary>
    public static string Python
    {
        get
        {
            foreach (var name in new[] { @"runtime\python.exe", @"runtime\python\python.exe" })
            {
                var file = Path.Combine(Root, name);
                if (File.Exists(file)) return file;
            }
            return "";
        }
    }

    /// <summary>config\ of the project: the version, the history of paths.</summary>
    public static string ProjectConfig => Path.Combine(Root, "config");

    /// <summary>
    /// config\ of the window. A build run from bin\ keeps its own beside itself: a check must not
    /// rewrite the settings of the copy the owner works in.
    /// </summary>
    public static string Config
    {
        get
        {
            var dir = Path.Combine(Released ? Root : App, "config");
            Directory.CreateDirectory(dir);
            return dir;
        }
    }

    public static string Logs
    {
        get
        {
            var dir = Path.Combine(Released ? Root : App, "logs");
            Directory.CreateDirectory(dir);
            return dir;
        }
    }

    static string? _session;

    /// <summary>
    /// The folder of this window's life, in the temporary folder of the user: the values of a
    /// run, its result, the stop signal and the notes of the engine about its own Word. One per
    /// window, removed when the window closes.
    /// </summary>
    public static string Session
    {
        get
        {
            _session ??= Path.Combine(Path.GetTempPath(), $"address_window_{Process.GetCurrentProcess().Id}");
            // Made at every look: a cleaner of the temporary folder may take it away while the window stands for days.
            if (!Directory.Exists(_session)) Directory.CreateDirectory(_session);
            return _session;
        }
    }

    /// <summary>The session folder goes with the window; what cannot be removed is left to the system.</summary>
    public static void DropSession()
    {
        try { if (_session is not null && Directory.Exists(_session)) Directory.Delete(_session, recursive: true); } catch { }
    }

    public static string Version
    {
        get
        {
            try
            {
                using var doc = System.Text.Json.JsonDocument.Parse(File.ReadAllText(Path.Combine(ProjectConfig, "version.json")));
                return doc.RootElement.TryGetProperty("version", out var v) ? v.GetString() ?? "" : "";
            }
            catch { return ""; }
        }
    }

    /// <summary>A path inside the project shown from its root, any other as it is.</summary>
    public static string Short(string path)
    {
        if (string.IsNullOrEmpty(path)) return "";
        try
        {
            var full = Path.GetFullPath(path);
            if (string.Equals(full, Root, StringComparison.OrdinalIgnoreCase)) return ".";
            if (full.StartsWith(Root + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase)) return full[(Root.Length + 1)..];
            return full;
        }
        catch { return path; }
    }

    /// <summary>What a person typed or picked as a full path: a relative one is counted from the project root.</summary>
    public static string Full(string path)
    {
        var text = (path ?? "").Trim().Trim('"');
        if (text.Length == 0) return "";
        try { return Path.GetFullPath(Path.IsPathRooted(text) ? text : Path.Combine(Root, text)); }
        catch { return text; }
    }
}
