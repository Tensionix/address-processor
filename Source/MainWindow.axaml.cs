using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.Documents;
using Avalonia.Input;
using Avalonia.Layout;
using Avalonia.Media;
using Avalonia.Threading;
using AudionAddressProcessor.Core;
using AudionAddressProcessor.Views;

namespace AudionAddressProcessor;

/// <summary>
/// The window of Audion Address Processor: the sections of the layout in a band, the operations of
/// a section with their forms on the left, the working folders, the result of the last run and the
/// journal on the right. It processes no address and decides nothing about addresses - every button
/// runs an operation of the manifest through the console command (address_cli.cmd), and the window
/// shows what the operation says.
///
/// The parts: this file - the shell (the header, the journal, the status line, the end);
/// MainWindow.Nav.cs - the bands of sections and operations and the cards; MainWindow.Io.cs - the
/// working folders; MainWindow.Run.cs - a run, its course, its result and STOP;
/// MainWindow.Sheets.cs - ABOUT and the service menu; MainWindow.Check.cs - the self-check.
/// </summary>
public partial class MainWindow : Window
{
    const string AppTitle = "Audion Address Processor";

    readonly Settings _settings;
    readonly Runner _runner = new();
    readonly Values _values = new();
    readonly Server _server = new();
    readonly Form _form;

    /// <summary>The manifest as the command told it at the start; null until it has, or when it could not.</summary>
    Manifest? _manifest;

    /// <summary>The width of the right column as the markup gives it: the one a person has not changed.</summary>
    double _sideOfMarkup;

    public MainWindow() : this(Settings.Load()) { }

    public MainWindow(Settings settings)
    {
        _settings = settings;
        _form = new Form(_values, this, _server, () => _manifest);
        App.SetFontStep(settings.FontStep);
        InitializeComponent();
#if DEBUG
        DevSetup();
#endif

        if (settings.Width >= MinWidth && settings.Height >= MinHeight) { Width = settings.Width; Height = settings.Height; }
        _sideOfMarkup = Zones.ColumnDefinitions[2].Width.Value;
        if (settings.Side >= Side.MinWidth) Zones.ColumnDefinitions[2].Width = new GridLength(settings.Side);
        VersionText.Text = "v" + Paths.Version;
        Title = AppTitle;

        WireTop();
        WireIo();
        WireJournal();
        WireRun();
        WireSheets();

        Journal.Lines += OnJournal;
        SafeFile.Problem += Say;
        Lang.Follow(StatusText);

        SetState("idle");
        ShowResult(null);

        Opened += (_, _) => Start();
        Closing += OnClosing;
    }

    /// <summary>
    /// The first lines of the journal: where the program is and what it runs. Then the manifest,
    /// read by the console command - the window draws nothing of its own.
    /// </summary>
    async void Start()
    {
        Lang.Walk(this);
        Journal.Add(Lang.F("программа: {0}", Paths.Root));
        foreach (var problem in SafeFile.Pending) Say(problem);
        SafeFile.Pending.Clear();

        if (Door.Trouble is { Length: > 0 } trouble)
        {
            Journal.Add(Lang.T("[окно] ") + trouble);
            NoManifest(trouble);
            return;
        }
        Journal.Add(Lang.F("консольная команда: {0}", Paths.Door));
        Say("читаю манифест…");
        var (manifest, why) = await Door.Describe();
        if (manifest is null)
        {
            Journal.Add(Lang.F("[окно] манифест не прочитан: {0}", why));
            NoManifest(Lang.F("манифест не прочитан: {0}", why));
            return;
        }
        _manifest = manifest;
        EnsureFolders();
        ResetPaths(quiet: true);
        BuildBadges();
        BuildService();
        BuildSections();
        // No box of the form holds the focus at the start: a key pressed by chance types nothing.
        Shell.Focus();
        var operations = manifest.Operations().Count();
        SayAs(() => Lang.F("готово к работе · операций {0}", operations));
#if DEBUG
        RunDevScript();
#endif
    }

    /// <summary>The window without a manifest: nothing to run, and the left zone says why.</summary>
    void NoManifest(string why)
    {
        Cards.Children.Clear();
        CardsNote.Text = why;
        CardsNote.IsVisible = true;
        OpBar.IsVisible = false;
        Say(Lang.T("запуск невозможен: причина в журнале"), refused: true);
#if DEBUG
        RunDevScript();
#endif
    }

    // ------------------------------------------------------------ the header: language, look, size of the letters

    void WireTop()
    {
        LangRu.Click += (_, _) => SwitchLanguage("ru");
        LangEn.Click += (_, _) => SwitchLanguage("en");
        MarkLanguage();

        ThemeVault.Click += (_, _) => SetTheme("vault");
        ThemeDark.Click += (_, _) => SetTheme("dark");
        ThemeCode.Click += (_, _) => SetTheme("codedark");
        ThemeLight.Click += (_, _) => SetTheme("light");
        MarkTheme();

        FontButton.Click += (_, _) =>
        {
            _settings.FontStep = _settings.FontStep switch { 0 => 1, 1 => -1, _ => 0 };
            _settings.Save();
            App.SetFontStep(_settings.FontStep);
            Say(Lang.T(_settings.FontStep switch { 1 => "шрифт крупнее", -1 => "шрифт мельче", _ => "шрифт обычный" }), refused: false, passing: true);
        };
    }

    DateTime _listsAt = DateTime.MinValue;

    /// <summary>
    /// The window is brought back (from Excel, where a workbook was changed): the lists the engine builds from files - the
    /// sheets, the headers of the first row - are read again, so no button to refresh them is needed.
    /// </summary>
    async void ReadListsAgain()
    {
        if (_manifest is null || _runner.Running || _finishing || (DateTime.Now - _listsAt).TotalSeconds < 3) return;
        _listsAt = DateTime.Now;
        if (_server.IsUp) await _server.ForgetOptions();
        _form.SourceChanged();
    }

    void MarkLanguage()
    {
        LangRu.IsChecked = Lang.Code == "ru";
        LangEn.IsChecked = Lang.Code == "en";
    }

    void SwitchLanguage(string next)
    {
        if (Lang.Code == next) { MarkLanguage(); return; }
        Lang.Set(next);
        _settings.Lang = next;
        _settings.Save();
        MarkLanguage();
        // What the manifest gives in two languages is built again; what the markup holds is walked.
        BuildClearMenu();
        if (_manifest is not null) { BuildBadges(); BuildService(); BuildSections(); }
        ShowState();
        ShowResult(_result);
        if (_steadyMake is { } make) SayAs(make);
        if (_runNode is not null && _runner.Running) Title = AppTitle + " — " + _runName;
        Lang.Walk(this);
    }

    void SetTheme(string look)
    {
        _settings.Look = look;
        _settings.Save();
        if (Application.Current is { } app) app.RequestedThemeVariant = App.Variant(look);
        Classes.Set("vault", look == "vault");
        MarkTheme();
        // The lines of the journal took their brushes from the old theme.
        Dispatcher.UIThread.Post(Recolour, DispatcherPriority.Background);
    }

    void MarkTheme()
    {
        ThemeVault.IsChecked = _settings.Look == "vault";
        ThemeDark.IsChecked = _settings.Look == "dark";
        ThemeCode.IsChecked = _settings.Look == "codedark";
        ThemeLight.IsChecked = _settings.Look == "light";
        ThemeButton.IsChecked = false;
    }

    // ------------------------------------------------------------ the status line

    /// <summary>idle, run, done, failed or stopped.</summary>
    string _state = "idle";

    static readonly string[] States = { "idle", "run", "done", "failed", "stopped" };

    void SetState(string state)
    {
        _state = state;
        ShowState();
    }

    void ShowState()
    {
        foreach (var known in States)
        {
            StateDot.Classes.Set(known, known == _state && known != "idle");
            StateText.Classes.Set(known, known == _state && known != "idle");
        }
        StateText.Text = Lang.T(StateName(_state));
    }

    static string StateName(string state) => state switch
    {
        "run" => "ВЫПОЛНЯЕТСЯ",
        "done" => "ГОТОВО",
        "failed" => "ОШИБКА",
        "stopped" => "ОСТАНОВЛЕНО",
        _ => "ОЖИДАНИЕ",
    };

    DispatcherTimer? _sayTimer;
    string _steady = "";

    /// <summary>How the steady line is made, when it depends on the language: it is made again when the language changes.</summary>
    Func<string>? _steadyMake;

    /// <summary>
    /// A word of the window in the status line. A short one - a refusal, "the choice was
    /// cancelled" - stays a few seconds and gives the line back to what stood there; a refusal is
    /// amber and goes to the journal too.
    /// </summary>
    void Say(string text) => Say(text, refused: false);

    void Say(string text, bool refused, bool passing = false)
    {
        _sayTimer?.Stop();
        StatusText.Classes.Set("refused", refused);
        StatusText.Text = text;
        if (refused) Journal.Add(Lang.T("[окно] ") + Lang.T(text));
        if (!refused && !passing) { _steady = text; _steadyMake = null; return; }
        _sayTimer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(refused ? 6 : 3) };
        _sayTimer.Tick += (_, _) =>
        {
            _sayTimer?.Stop();
            StatusText.Classes.Set("refused", false);
            StatusText.Text = _steady;
        };
        _sayTimer.Start();
    }

    /// <summary>A steady line whose words are chosen again after a change of language.</summary>
    void SayAs(Func<string> make)
    {
        Say(make());
        _steadyMake = make;
    }

    /// <summary>A folder or a file, by the program Windows opens it with.</summary>
    void Open(string path)
    {
        if (!Directory.Exists(path) && !File.Exists(path)) { Say(Lang.F("нет на диске: {0}", Paths.Short(path)), refused: true); return; }
        try { Process.Start(new ProcessStartInfo(path) { UseShellExecute = true }); }
        catch (Exception ex) { Journal.Add(Lang.F("[окно] не запустилось: {0}", ex.Message)); }
    }

    /// <summary>A file shown in Explorer with the selection on it; a folder opened.</summary>
    void Reveal(string path)
    {
        if (File.Exists(path))
        {
            try { Process.Start(new ProcessStartInfo("explorer.exe") { ArgumentList = { "/select,", path } }); }
            catch (Exception ex) { Journal.Add(Lang.F("[окно] не запустилось: {0}", ex.Message)); }
            return;
        }
        Open(path);
    }

    // ------------------------------------------------------------ the journal

    /// <summary>The text of the journal panel since it was last cleared: the copy button gives all of it, up to a limit.</summary>
    readonly StringBuilder _logAll = new();
    const int LogAllLimit = 16_000_000;

    /// <summary>
    /// The panel keeps the last lines of a run and not all of them. It is pages of text one under
    /// another: a text is laid out whole at every line added to it, so new lines go into the last
    /// page while it has room, a full page is never touched again, and the oldest pages leave whole.
    /// </summary>
    const int LogLimit = 5000;
    const int PageLines = 100;
    readonly List<int> _pageLines = new();
    readonly List<int> _pageRuns = new();
    readonly List<(Run Run, LogTone Tone)> _logRuns = new();
    int _logShown;
    bool _scrollPosted;

    void WireJournal()
    {
        LogsButton.Click += (_, _) => Open(_manifest?.Paths.Logs is { Length: > 0 } logs ? logs : Path.Combine(Paths.Root, "logs"));
        ReportsButton.Click += (_, _) => Open(_manifest?.Paths.Report is { Length: > 0 } report ? report : Path.Combine(Paths.Root, "report"));
        ConfigButton.Click += (_, _) => Open(Paths.ProjectConfig);

        ClearLogButton.Click += (_, _) => { ClearLogPanel(); Say("панель журнала очищена", refused: false, passing: true); };
        CopyLogButton.Click += async (_, _) =>
        {
            if (Clipboard is { } clipboard) await Avalonia.Input.Platform.ClipboardExtensions.SetTextAsync(clipboard, _logAll.ToString());
            Say("журнал в буфере обмена", refused: false, passing: true);
        };
        WideLogButton.Click += (_, _) => SetWideLog(!_wideLog);
    }

    bool _wideLog;
    GridLength _resultRow = GridLength.Auto;

    /// <summary>The journal over the whole right column - the working folders and the result give it their place - and back.</summary>
    void SetWideLog(bool wide)
    {
        _wideLog = wide;
        var rows = Side.RowDefinitions;
        foreach (var child in Side.Children)
            if (child is Control control && Grid.GetRow(control) < 2) control.IsVisible = !wide;
        rows[0].Height = wide ? new GridLength(0) : GridLength.Auto;
        rows[1].Height = wide ? new GridLength(0) : _resultRow;
        if (WideLogButton.Content is Avalonia.Controls.Shapes.Path sign)
        {
            sign.Tag = wide ? "minimize-2" : "maximize-2";
            sign.Data = Icons.Glyph(wide ? "minimize-2" : "maximize-2");
        }
    }

    void ClearLogPanel()
    {
        LogPages.Children.Clear();
        _pageLines.Clear();
        _pageRuns.Clear();
        _logRuns.Clear();
        _logAll.Clear();
        _logShown = 0;
        HideActivity();
    }

    static string ToneKey(LogTone tone) => tone switch
    {
        LogTone.Muted => "LogMuted", LogTone.Head => "LogHead", LogTone.Good => "LogGood",
        LogTone.Warn => "LogWarn", LogTone.Bad => "LogBad", _ => "LogPlain",
    };

    void OnJournal(IReadOnlyList<(string Text, LogTone Tone)> lines)
    {
        if (!Dispatcher.UIThread.CheckAccess()) { Dispatcher.UIThread.Post(() => OnJournal(lines)); return; }
        AppendLines(lines);
    }

    /// <summary>Lines into the panel, each in the tone of what it says.</summary>
    void AppendLines(IReadOnlyList<(string Text, LogTone Tone)> lines)
    {
        if (lines.Count == 0) return;
        // The panel follows the new lines while its reader is at the end, and stays where it is
        // when he has gone up to read: asked before the lines are added.
        bool follow = _scrollPosted || LogScroll.Offset.Y + LogScroll.Viewport.Height >= LogScroll.Extent.Height - 40;
        foreach (var (text, _) in lines) _logAll.Append(text).Append("\r\n");
        if (_logAll.Length > LogAllLimit)
        {
            int cut = LogAllLimit / 4;
            while (cut < _logAll.Length && _logAll[cut - 1] != '\n') cut++;
            _logAll.Remove(0, cut);
        }

        int at = Math.Max(0, lines.Count - LogLimit);
        _logShown += lines.Count - at;
        var pages = LogPages.Children;
        while (at < lines.Count)
        {
            if (_pageLines.Count == 0 || _pageLines[^1] >= PageLines)
            {
                pages.Add(new Controls.LogPage { TextWrapping = TextWrapping.Wrap });
                _pageLines.Add(0);
                _pageRuns.Add(0);
            }
            int held = _pageLines[^1], take = Math.Min(PageLines - held, lines.Count - at);
            var page = (Controls.LogPage)pages[^1];
            var inlines = page.Inlines ??= new InlineCollection();
            for (int i = 0; i < take; i++)
            {
                var (text, tone) = lines[at + i];
                var run = new Run((held + i > 0 ? "\n" : "") + text) { Foreground = App.Ink(ToneKey(tone)) };
                inlines.Add(run);
                _logRuns.Add((run, tone));
            }
            _pageLines[^1] = held + take;
            _pageRuns[^1] += take;
            at += take;
        }

        int gone = 0, lost = 0;
        while (gone < _pageLines.Count - 1 && _logShown - _pageLines[gone] >= LogLimit)
        {
            _logShown -= _pageLines[gone];
            lost += _pageRuns[gone++];
        }
        if (gone > 0)
        {
            pages.RemoveRange(0, gone);
            _pageLines.RemoveRange(0, gone);
            _pageRuns.RemoveRange(0, gone);
            _logRuns.RemoveRange(0, lost);
        }

        if (!follow || _scrollPosted) return;
        _scrollPosted = true;
        Dispatcher.UIThread.Post(() =>
        {
            _scrollPosted = false;
            LogScroll.ScrollToEnd();
        }, DispatcherPriority.Background);
    }

    /// <summary>After a theme change the lines already written keep their meaning and take the new colours.</summary>
    void Recolour()
    {
        foreach (var (run, tone) in _logRuns) run.Foreground = App.Ink(ToneKey(tone));
    }

    // ------------------------------------------------------------ the live line

    DispatcherTimer? _breath;

    /// <summary>
    /// The bar a long stage rewrites in place is one line under the journal, not a hundred lines in it:
    /// the percent in the colour of the accent, the rest quiet, behind a dot that breathes.
    /// </summary>
    void ShowActivity(string text)
    {
        ActivityRow.IsVisible = true;
        LiveLine.Paint(ActivityText, text);
        if (_breath is not null) return;
        bool dim = false;
        _breath = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(650) };
        _breath.Tick += (_, _) => ActivityDot.Opacity = (dim = !dim) ? 0.35 : 1;
        _breath.Start();
    }

    void HideActivity()
    {
        _breath?.Stop();
        _breath = null;
        ActivityDot.Opacity = 1;
        ActivityRow.IsVisible = false;
        ActivityText.Inlines?.Clear();
    }

    // ------------------------------------------------------------ the end

    void SaveWindow()
    {
        if (WindowState == WindowState.Normal)
        {
            _settings.Width = Width;
            _settings.Height = Height;
        }
        // Only a width the person chose is kept. The width of the markup is written as 0, "by default":
        // a number saved at every close would hold the window at the former default after the markup
        // has changed it.
        double side = Zones.ColumnDefinitions[2].ActualWidth;
        _settings.Side = Math.Abs(side - _sideOfMarkup) < 0.5 ? 0 : side;
        _settings.Save();
    }
}
