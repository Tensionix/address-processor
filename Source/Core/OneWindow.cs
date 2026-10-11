using System;
using System.Diagnostics;
using System.Linq;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Threading;

namespace AudionAddressProcessor.Core;

/// <summary>
/// One window per folder of the program. The four Build tools work with one release root, the
/// one of the orchestrator, so two windows of one program would run two commands over the same
/// folders at once, write one journal of the day and take turns at rewriting the settings. A
/// second start brings the window that is open forward and ends. Per folder of the program: a
/// copy in another folder - a stand of a check - runs by itself.
/// </summary>
public static class OneWindow
{
    // Held as long as the program lives: Windows lets the name go with the process.
    static Mutex? _held;
    static string _program = "";

    static string Name(string program)
    {
        var folder = Paths.Root.TrimEnd('\\', '/').ToLowerInvariant();
        return @"Local\" + program + "-" + Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(folder)))[..24];
    }

    /// <summary>
    /// True - this is the only window of its folder. False - another one is open: it was brought
    /// forward, and this start has nothing to do but end.
    /// </summary>
    public static bool Claim(string program)
    {
        _program = program;
        var name = Name(program);
        try
        {
            _held = new Mutex(true, name, out bool first);
            if (first) return true;
            _held.Dispose();
            _held = null;
        }
        // A window started with other rights holds the name, and this start may not even open
        // it: the window is there all the same.
        catch (UnauthorizedAccessException) { }
        // Windows gave no name at all: better two windows than none.
        catch { return true; }
        BringForward();
        return false;
    }

    [DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr window);
    [DllImport("user32.dll")] static extern bool ShowWindow(IntPtr window, int command);
    [DllImport("user32.dll")] static extern bool IsIconic(IntPtr window);

    /// <summary>The window of the copy that is already open: restored when minimised, put in front.</summary>
    static void BringForward()
    {
        try
        {
            using var me = Process.GetCurrentProcess();
            var mine = me.MainModule?.FileName ?? "";
            foreach (var other in Process.GetProcessesByName(me.ProcessName).Where(process => process.Id != me.Id))
            {
                string path;
                try { path = other.MainModule?.FileName ?? ""; } catch { continue; }
                if (!string.Equals(path, mine, StringComparison.OrdinalIgnoreCase) || other.MainWindowHandle == IntPtr.Zero) continue;
                if (IsIconic(other.MainWindowHandle)) ShowWindow(other.MainWindowHandle, 9);
                SetForegroundWindow(other.MainWindowHandle);
                return;
            }
        }
        catch { }
    }
}
