#if DEBUG
using System;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.Primitives;
using Avalonia.Media.Imaging;
using Avalonia.VisualTree;
using AudionAddressProcessor.Core;

namespace AudionAddressProcessor;

/// <summary>
/// A way to check the window without a mouse - a real pointer clicks into whatever window is in
/// front, and that may be the owner's. A Debug build alone reads AUDION_DEV_SCRIPT: steps
/// separated by ";", run one after another once the window has read the manifest:
///   section=ID | op=ID | set=FIELD=VALUE | reset | source=PATH | target=PATH | choose=source:PATH |
///   pin=source | paths=reset | history=source | clear=source|target|both | run=OPERATION | stop |
///   answer=yes | answer=yes,yes | say=OPERATION | press=AUTOMATIONID | lang=en | theme=light |
///   size=1400x860 | log=wide | log=normal | sheet=about | list | wait=3 | idle | shot=file.png |
///   dump | crash=ui | close
/// "idle" waits until the manifest is read and no operation runs. "say" writes what a press would
/// start, without starting it. "press" presses the button with that AutomationId - through the very
/// handler a click reaches. "dump" writes what the left zone holds. The window of a script is not
/// shown to the person at the machine: it stands beyond the screen (AUDION_SHOT_ON_SCREEN=1 brings it
/// back), and the pictures are drawn by Avalonia itself. A release build has none of this.
/// </summary>
public partial class MainWindow
{
    bool _devDone;

    /// <summary>Before the window does anything: the keyboard and the screen are left to whoever sits at the machine.</summary>
    void DevSetup()
    {
        if (string.IsNullOrWhiteSpace(Environment.GetEnvironmentVariable("AUDION_DEV_SCRIPT"))) return;
        ShowActivated = false;
        if (Environment.GetEnvironmentVariable("AUDION_SHOT_ON_SCREEN") == "1") return;
        ShowInTaskbar = false;
        WindowStartupLocation = WindowStartupLocation.Manual;
        Position = new PixelPoint(-32000, -32000);
    }

    Node? DevNode(string id)
    {
        var node = _manifest?.Find(id);
        if (node is null) Journal.Add("[dev] no such node: " + id);
        return node;
    }

    async void RunDevScript()
    {
        if (_devDone) return;
        _devDone = true;
        var script = Environment.GetEnvironmentVariable("AUDION_DEV_SCRIPT");
        if (string.IsNullOrWhiteSpace(script)) return;
        await Task.Delay(600);
        foreach (var raw in script.Split(';', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
        {
            var parts = raw.Split('=', 2);
            var value = parts.Length > 1 ? parts[1] : "";
            try
            {
                switch (parts[0])
                {
                    case "section":
                        if (_manifest?.Layout.Sections.FirstOrDefault(section => section.Id == value) is { } section) SelectSection(section);
                        else Journal.Add("[dev] no such section: " + value);
                        break;
                    case "op":
                        if (_manifest?.Layout.Sections.FirstOrDefault(section => section.Operations.Any(placed => placed.Id == value)) is { } owner)
                        {
                            if (_section?.Id != owner.Id) SelectSection(owner);
                            SelectOperation(owner.Operations.First(placed => placed.Id == value));
                        }
                        else Journal.Add("[dev] no such operation in the layout: " + value);
                        break;
                    case "set" when value.Split('=', 2) is [var id, var text]:
                        if (_node?.Fields.FirstOrDefault(field => field.Id == id) is { } field)
                            _values.Set(field, text.Replace("|", Values.ListSeparator.ToString()));
                        else Journal.Add("[dev] no such field in the open operation: " + id);
                        break;
                    case "reset":
                        if (_manifest is not null) _values.Reset(_manifest.All().SelectMany(node => node.Fields));
                        break;
                    case "source": SetSource(value); break;
                    case "target": SetTarget(value); break;
                    // A path chosen as a person chooses it: set and remembered in the history.
                    case "choose" when value.Split(':', 2) is [var role, var chosen]: Choose(role == "source", chosen); break;
                    case "pin": TogglePin(value == "source"); break;
                    case "paths": ResetPaths(quiet: false); break;
                    case "history":
                        foreach (var entry in _history?.Entries(value == "source") ?? new())
                            Journal.Add($"[dev] history {value}: {(entry.Pinned ? "pinned " : "")}{entry.Path} x{entry.Count}");
                        break;
                    // A check clears only folders of its own: a path inside the project is refused here,
                    // whatever the script says - input and output hold the owner's files.
                    case "clear":
                    {
                        bool source = value is "source" or "both", target = value is "target" or "both";
                        bool Inside(string path) => (path + "\\").StartsWith(Paths.Root + "\\", StringComparison.OrdinalIgnoreCase);
                        if ((source && Inside(_source)) || (target && Inside(_target)))
                        {
                            Journal.Add("[dev] refused: a check never clears a folder of the project");
                            break;
                        }
                        ClearFolders(source, target);
                        break;
                    }
                    case "run":
                        if (DevNode(value) is { } operation) Press(operation);
                        break;
                    case "stop": StopRun(); break;
                    // The answer to the next question of the window: "yes" or "no".
                    case "answer": Views.Dialog.DevAnswer = value; break;
                    // What a press would start, into the journal - without starting it.
                    case "say":
                        if (DevNode(value) is { } asked)
                        {
                            Journal.Add("[dev] console: " + Door.RunLine(asked.Id, _source, _target, _values.ChangedOf(asked)));
                            Journal.Add("[dev] params: " + _values.ForDoor(asked).Replace("\r", "").Replace("\n", " "));
                        }
                        break;
                    // A button pressed by its AutomationId: the handler a click reaches, not the method behind it.
                    case "press":
                    {
                        var target = this.GetVisualDescendants().OfType<Button>().FirstOrDefault(button => Avalonia.Automation.AutomationProperties.GetAutomationId(button) == value)
                            ?? (Control?)this.GetVisualDescendants().OfType<ToggleButton>().FirstOrDefault(button => Avalonia.Automation.AutomationProperties.GetAutomationId(button) == value);
                        if (target is null) { Journal.Add("[dev] no button with the id: " + value); break; }
                        Journal.Add($"[dev] press {value}: enabled {target.IsEnabled}, visible {target.IsEffectivelyVisible}");
                        if (target.IsEnabled) target.RaiseEvent(new Avalonia.Interactivity.RoutedEventArgs(Button.ClickEvent));
                        break;
                    }
                    case "sheet": if (_sheet != value) ToggleSheet(value); break;
                    case "lang": SwitchLanguage(value); break;
                    case "theme": SetTheme(value); break;
                    case "size" when value.Split('x') is [var w, var h]: Width = double.Parse(w); Height = double.Parse(h); break;
                    case "log": SetWideLog(value == "wide"); break;
                    case "list": ListSourceFiles(); break;
                    case "wait": await Task.Delay(TimeSpan.FromSeconds(double.Parse(value, System.Globalization.CultureInfo.InvariantCulture))); break;
                    case "idle":
                        await Task.Delay(400);
                        for (int i = 0; i < 7200 && _runner.Running; i++) await Task.Delay(500);
                        await Task.Delay(300);
                        break;
                    // The window drawn into a file by Avalonia itself: nothing is put on top of the owner's windows.
                    case "shot":
                    {
                        await Task.Delay(500);
                        var scale = RenderScaling;
                        var size = new PixelSize(Math.Max(1, (int)(Bounds.Width * scale)), Math.Max(1, (int)(Bounds.Height * scale)));
                        using var bitmap = new RenderTargetBitmap(size, new Vector(96 * scale, 96 * scale));
                        bitmap.Render(this);
                        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(value))!);
#pragma warning disable CS0618
                        bitmap.Save(value);
#pragma warning restore CS0618
                        Journal.Add($"[dev] shot {value} {size.Width}x{size.Height} scale {scale}");
                        break;
                    }
                    // What the window holds now, in words: the section, the band of operations, the card and its size.
                    case "dump":
                        Journal.Add($"[dev] section {_section?.Id}; operation {_node?.Id}; band: {OpRow.Children.Count} items, {OpRow.Bounds.Width:0}x{OpRow.Bounds.Height:0}; card: {Cards.Bounds.Width:0}x{Cards.Bounds.Height:0} in {CardScroll.Viewport.Width:0}x{CardScroll.Viewport.Height:0}");
                        break;
                    // An error nobody catches, thrown on purpose - the guard must keep the window and write logs\gui-crash-*.log.
                    case "crash":
                        Avalonia.Threading.Dispatcher.UIThread.Post(() => throw new InvalidOperationException("dev: an error thrown on purpose in the thread of the window"));
                        break;
                    case "close": Close(); break;
                    default: Journal.Add("[dev] unknown step: " + raw); break;
                }
            }
            catch (Exception ex) { Journal.Add($"[dev] {raw}: {ex.Message}"); }
            await Task.Delay(250);
        }
        Journal.Add("[dev] script done");
    }
}
#endif
