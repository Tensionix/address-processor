using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Input;
using Avalonia.Threading;
using AudionAddressProcessor.Core;
using AudionAddressProcessor.Views;

namespace AudionAddressProcessor;

/// <summary>
/// A run: one operation at a time, started through the console command with what the form and the
/// working folders hold at the moment of the press. Its course is read from the service lines of the
/// command, its result from the file the command writes. STOP asks the operation to stop - it ends
/// at its next safe point and closes the Excel and Word it opened; only an operation that does not
/// answer is ended from here.
/// </summary>
public partial class MainWindow
{
    /// <summary>The operation that runs or ran last.</summary>
    Node? _running;
    /// <summary>The operation that runs (or ran last): its name is asked when it is shown, so it follows the language.</summary>
    Node? _runNode, _resultNode;
    string _runName => _runNode?.Name ?? "";
    string _resultName => _resultNode?.Name ?? "";
    DateTime _started;
    readonly DispatcherTimer _clock = new() { Interval = TimeSpan.FromSeconds(1) };

    /// <summary>What the command said of the run in its service lines.</summary>
    DoorEvent? _finish;
    string _runLog = "", _runReports = "";

    bool _stopAsked, _killed;
    DispatcherTimer? _killTimer;
    /// <summary>How long an operation asked to stop is waited for before it is ended.</summary>
    const int StopWaitSeconds = 60;

    /// <summary>The result of the last run, for the panel; null until something has run.</summary>
    RunResult? _result;
    string _outcome = "", _took = "", _resultTarget = "";

    void WireRun()
    {
        _runner.Output += OnOutput;
        // Brought back to the front (from Excel, say): the lists made from files are read again.
        Activated += (_, _) => ReadListsAgain();
        _runner.RunningChanged += ApplyBusy;
        _runner.Finished += OnFinished;
        StopButton.Click += (_, _) => StopRun();
        _clock.Tick += (_, _) => ShowClock();

        // Ctrl+Enter runs the operation of the card in sight.
        AddHandler(KeyDownEvent, (_, e) =>
        {
            if (e.Key != Key.Enter || e.KeyModifiers != KeyModifiers.Control) return;
            // A sheet over the window (About) hides the card: nothing is run from behind it.
            if (_sheet.Length > 0) return;
            e.Handled = true;
            // A number or a path being typed is taken first: its box gives up the focus.
            Shell.Focus();
            if (CardOperation() is { } operation) Press(operation);
            else Say("нет открытой карточки операции", refused: false, passing: true);
        }, Avalonia.Interactivity.RoutingStrategies.Tunnel);

        ResultReportButton.Click += (_, _) => ShowReport();
        ResultFolderButton.Click += (_, _) => { if (ResultFolder() is { Length: > 0 } folder) Open(folder); };
        ResultToSourceButton.Click += (_, _) =>
        {
            if (_runner.Running) { Say("идёт операция: пути не меняются", refused: true); return; }
            if (ResultOwnFolder() is not { Length: > 0 } folder) return;
            SetSource(folder);
            Say(Lang.F("источник: {0}", Paths.Short(folder)), refused: false, passing: true);
        };
    }

    /// <summary>One operation at a time: while it goes, nothing else starts and the folders it began with stay.</summary>
    void ApplyBusy(bool running)
    {
        bool free = !running && !_finishing && _manifest is not null && Door.Ready;
        foreach (var button in _runButtons) button.IsEnabled = free;
        foreach (var control in new Control[] { SourceBox, TargetBox, PickFolderButton, PickFileButton, PickTargetButton, ResetPathsButton, ClearFoldersButton, ServiceButton })
            control.IsEnabled = !running && !_finishing;
        // A clearing that is going keeps its own button shut whatever a run does.
        if (_clearing) ClearFoldersButton.IsEnabled = false;
        StopButton.IsVisible = running;
        StopButton.IsEnabled = running && !_stopAsked;
        if (!running) Title = AppTitle;
    }

    // ------------------------------------------------------------ the start

    /// <summary>
    /// A press of a button that runs an operation. Everything the run needs is taken from the
    /// window here, before any question: the answer may come a minute later, and what is started
    /// is what was asked about.
    /// </summary>
    async void Press(Node? node)
    {
        if (node is null || !node.Runs) return;
        if (_runner.Running || _finishing) { Say("идёт другая операция", refused: true); return; }
        if (_clearing) { Say("идёт очистка папок", refused: true); return; }
        if (_manifest is null || !Door.Ready) { Say("запуск невозможен: причина в журнале", refused: true); return; }

        var source = _source;
        var target = _target;
        // The cleaning of the program's own folders cleans those, whatever the window points at: its name says input and output.
        if (node.Id == _manifest.Layout.Workspace.Clear) { source = DefaultSource; target = DefaultTarget; }
        if (!Directory.Exists(source) && !File.Exists(source)) { Say(Lang.F("источника нет на диске: {0}", source), refused: true); return; }
        foreach (var field in node.FormFields.Where(field => field.Kind == "checkboxes" && field.MinSelected > 0 && _values.IsShown(node, field)))
        {
            if (_values.Picked(field).Count >= field.MinSelected) continue;
            Say(Lang.F("«{0}»: отметьте не меньше {1}", field.Name, field.MinSelected), refused: true);
            return;
        }
        var values = _values.ForDoor(node);
        var changed = _values.ChangedOf(node);

        if (node.Kind == "dangerous")
        {
            var lines = new List<string> { Lang.F("Источник: {0}", source), Lang.F("Назначение: {0}", target) };
            if (node.About.Length > 0) { lines.Add(""); lines.Add(node.About); }
            lines.Add("");
            lines.Add("Проверьте, что нужные исходники и результаты уже сохранены вне очищаемых папок.");
            var go = await Dialog.Ask(this, Lang.F("Выполнить «{0}»?", node.Name), lines, "ВЫПОЛНИТЬ", Tone.Danger);
            if (go is null) return;
            // A second press while the question stood, or the window on its way out.
            if (_runner.Running || !IsVisible) return;
        }
        Begin(node, source, target, values, changed);
    }

    /// <summary>A run has ended but the window has not finished with it (the result, the Excel and Word it leaves): nothing else starts.</summary>
    bool _finishing;

    void Begin(Node node, string source, string target, string values, Dictionary<string, string> changed)
    {
        _finishing = true;
        _running = node;
        _runNode = node;
        _started = DateTime.Now;
        _finish = null;
        _runLog = _runReports = "";
        _stopAsked = _killed = false;
        _resultTarget = target;

        // The panel of the journal begins anew with every run; the files in logs keep everything.
        ClearLogPanel();
        Journal.Add($"===== {_runName} =====");
        // The same run as a console would type it.
        Journal.Add(Lang.T("[окно] ") + Door.RunLine(node.Id, source, target, changed));

        _result = null;
        _outcome = "run";
        _resultNode = _runNode;
        ShowResult(null);

        if (!Door.Prepare(values)) { OnFinished(-1); return; }
        // A failed start has told the journal and raised Finished itself.
        if (!_runner.Start(Door.Make(Door.RunArgs(node.Id, source, target)))) return;

        SetState("run");
        SayAs(() => _runName);
        Title = AppTitle + " — " + _runName;
        // Until the operation says how far it is, the bar only shows that it goes.
        ProgressBar.IsVisible = true;
        ProgressBar.IsIndeterminate = true;
        CourseText.Text = "";
        ShowClock();
        _clock.Start();
    }

    // ------------------------------------------------------------ the course

    void OnOutput(IReadOnlyList<string> lines)
    {
        var plain = new List<string>(lines.Count);
        foreach (var line in lines)
        {
            if (Door.Read(line) is not { } said) { plain.Add(line); continue; }
            switch (said.Kind)
            {
                case "started":
                    _runLog = said.Log;
                    _runReports = said.ReportDir;
                    break;
                case "progress":
                    ShowProgress(said.Progress);
                    break;
                case "live":
                    ShowActivity(said.Live);
                    break;
                case "finished":
                    _finish = said;
                    break;
            }
        }
        Journal.Show(plain);
    }

    void ShowProgress(double share)
    {
        // A share of zero is "started", not a measure: most operations say 0 and then 1.
        bool measured = share > 0;
        ProgressBar.IsIndeterminate = !measured;
        if (measured) ProgressBar.Value = Math.Max(2, Math.Min(100, share * 100));
        CourseText.Text = share > 0 ? $"{Math.Round(share * 100)}%" : "";
    }

    void ShowClock() => ClockText.Text = Clock(DateTime.Now - _started);

    static string Clock(TimeSpan span) => span.TotalHours >= 1 ? span.ToString(@"h\:mm\:ss") : span.ToString(@"mm\:ss");

    // ------------------------------------------------------------ STOP

    /// <summary>
    /// STOP. The operation is asked by the signal file: it sees the file itself and ends at its next
    /// safe point, closing the Excel and Word it opened. An operation that has not ended in a minute
    /// is ended from here, and its Office closed by its notes.
    /// </summary>
    void StopRun(bool closing = false)
    {
        if (!_runner.Running || _stopAsked) return;
        _stopAsked = true;
        StopButton.IsEnabled = false;
        Journal.Add(Lang.T(closing ? "[окно] остановлено закрытием окна: операция заканчивает работу"
            : "[окно] остановлено кнопкой СТОП: операция заканчивает работу"));
        SayAs(() => Lang.F("{0}: останавливается…", _runName));
        if (!Door.AskToStop())
        {
            HardStop();
            return;
        }
        _killTimer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(StopWaitSeconds) };
        _killTimer.Tick += (_, _) => HardStop();
        _killTimer.Start();
    }

    void HardStop()
    {
        _killTimer?.Stop();
        if (!_runner.Running) return;
        _killed = true;
        Journal.Add(Lang.F("[окно] операция не остановилась за {0} с: завершена принудительно", StopWaitSeconds));
        _runner.Kill();
    }

    // ------------------------------------------------------------ the end of a run

    async void OnFinished(int code)
    {
        try { await Finish(code); }
        finally
        {
            _finishing = false;
            ApplyBusy(_runner.Running);
        }
    }

    async Task Finish(int code)
    {
        _clock.Stop();
        _killTimer?.Stop();
        HideActivity();
        ShowClock();
        var took = Clock(DateTime.Now - _started);
        var result = Door.ReadResult();

        // What the command said comes first; a command that did not get to say it is read by its exit code.
        string outcome = _killed ? "stopped"
            : _finish is { Outcome.Length: > 0 } said ? said.Outcome
            : result is { Outcome.Length: > 0 } ? result.Outcome
            : code == Door.ExitStopped || _stopAsked ? "stopped"
            : code == -1 ? "nostart"
            : code == Door.ExitUsage ? "refused"
            : code == Door.ExitDone ? "done" : "failed";
        string verdict = outcome switch
        {
            "done" => "готово",
            "stopped" => "остановлено",
            "refused" => "отказ до начала",
            "nostart" => "не запустилось",
            _ => "ошибка",
        };
        Journal.Add($"===== {_runName}: {Lang.T(verdict)} · {took}");
        if (_runLog.Length > 0) Journal.Add(Lang.F("[окно] журнал операции: {0}", Paths.Short(_runLog)));

        // An operation ended from here could not quit its Excel and Word: its notes say which ones they were.
        // So is one that fell on its own: the notes are closed only by an operation that ended in order.
        if (_killed || outcome == "failed")
        {
            var (stopped, lost) = await Door.StopOffice();
            if (stopped > 0) Journal.Add(Lang.F("[окно] закрыто своих Excel и Word: {0}", stopped));
            if (lost > 0) Journal.Add(Lang.F("[окно] Excel или Word операции мог остаться открытым: {0} - проверьте диспетчер задач", lost));
        }

        ProgressBar.IsVisible = false;
        CourseText.Text = "";
        SetState(outcome switch { "done" => "done", "stopped" => "stopped", _ => "failed" });
        SayAs(() => outcome switch
        {
            "done" => _runName,
            "stopped" => _runName,
            "refused" => Lang.F("{0}: отказ до начала - причина в журнале", _runName),
            "nostart" => Lang.F("{0}: не запустилось - причина в журнале", _runName),
            _ => Lang.F("{0}: ошибка - подробности в журнале", _runName),
        });

        _result = result;
        _outcome = outcome;
        _took = took;
        ShowResult(result);
        // What an operation made lies in the folders now: the lists of a form that look at them are read again.
        _form.SourceChanged();
        // The Rosstat data may have changed (any operation may be the one that refreshed it): what the
        // process of questions read of it is old.
        if (_server.IsUp)
        {
            await _server.Forget();
            RefreshOktmo();
        }
        // The snapshot of the registry in the header may be a new one (the operation that refreshes it ended).
        if (_manifest is not null) BuildBadges();

        if (_closeAfterRun) Close();
    }

    // ------------------------------------------------------------ the result

    /// <summary>The folder the operation made its files in: the first file it named as its result, its folder. "" when it named none.</summary>
    string ResultOwnFolder()
    {
        foreach (var path in _result?.Outputs() ?? new List<string>())
        {
            var full = Paths.Full(path);
            if (Directory.Exists(full)) return full;
            if (File.Exists(full) && Path.GetDirectoryName(full) is { Length: > 0 } folder) return folder;
        }
        return "";
    }

    /// <summary>Where the last run put its result: the folder the operation named, else the target of the run.</summary>
    string ResultFolder() =>
        ResultOwnFolder() is { Length: > 0 } own ? own
        : _outcome == "done" && Directory.Exists(_resultTarget) ? _resultTarget : "";

    string ResultReport() => _result?.ReportFile() is { Length: > 0 } file && File.Exists(Paths.Full(file)) ? Paths.Full(file) : "";

    void ShowReport()
    {
        if (ResultReport() is { Length: > 0 } report) ReportView.Show(this, report);
        else if (_runReports.Length > 0 && Directory.Exists(_runReports)) Open(_runReports);
    }

    /// <summary>
    /// The panel of the result: the verdict in one word and its colour, what the operation made
    /// and where its files are.
    /// </summary>
    void ShowResult(RunResult? result)
    {
        foreach (var known in new[] { "run", "done", "failed", "stopped" })
            VerdictText.Classes.Set(known, known == (_outcome is "refused" or "nostart" ? "failed" : _outcome));
        ResultLines.Children.Clear();
        VerdictText.Text = _outcome switch
        {
            "" => Lang.T("операций в этом окне ещё не было"),
            "run" => Lang.F("{0} · идёт", _resultName),
            "done" => Lang.F("{0} · готово · {1}", _resultName, _took),
            "stopped" => Lang.F("{0} · остановлено · {1}", _resultName, _took),
            "refused" => Lang.F("{0} · отказ до начала", _resultName),
            "nostart" => Lang.F("{0} · не запустилось", _resultName),
            _ => Lang.F("{0} · ошибка · {1}", _resultName, _took),
        };

        bool ended = _outcome is not ("" or "run");
        ResultReportButton.IsEnabled = ended && (ResultReport().Length > 0 || (_runReports.Length > 0 && Directory.Exists(_runReports)));
        ResultFolderButton.IsEnabled = ended && ResultFolder().Length > 0;
        // Only what the operation called its result can be the next source: an operation that only
        // looks and reports has nothing to hand on.
        ResultToSourceButton.IsEnabled = _outcome == "done" && ResultOwnFolder().Length > 0;
        if (!ended) return;

        if (result?.Message is { Length: > 0 } message && _outcome != "done")
            ResultLines.Children.Add(new TextBlock { Classes = { "note" }, Text = message, TextWrapping = Avalonia.Media.TextWrapping.Wrap });
        void Place(string name, string path)
        {
            if (path.Length > 0) ResultLines.Children.Add(new TextBlock { Classes = { "note" }, Text = Lang.F(name, Paths.Short(path)), TextTrimming = Avalonia.Media.TextTrimming.CharacterEllipsis });
        }
        var made = result?.Outputs() ?? new List<string>();
        if (made.Count > 0)
            ResultLines.Children.Add(new TextBlock
            {
                Classes = { "note" }, TextTrimming = Avalonia.Media.TextTrimming.CharacterEllipsis,
                Text = Lang.F("результат: {0}", Paths.Short(made[0])) + (made.Count > 1 ? Lang.F(" · файлов: {0}", made.Count) : ""),
            });
        // The line names the first file; the others are in the tip (five of them, then the count).
        if (made.Count > 1 && ResultLines.Children.LastOrDefault() is TextBlock resultLine)
            ToolTip.SetTip(resultLine, string.Join("\n", made.Take(5).Select(Paths.Short)) + (made.Count > 5 ? "\n" + Lang.F("… и ещё {0}", made.Count - 5) : ""));
        Place("отчёт: {0}", ResultReport());
        Place("журнал: {0}", result?.Log is { Length: > 0 } log ? log : _runLog);
    }

    // ------------------------------------------------------------ the end of the window

    bool _closeAfterRun, _closeAsking;

    /// <summary>
    /// The window closes. An operation does not outlive it: an orphaned Python with its Excel would go
    /// on rewriting books nobody watches. So a running operation is asked about - closing stops it,
    /// and that has to be a decision - and on a "yes" it is stopped the way STOP stops it; the window
    /// closes when the operation has ended. Windows shutting down is not asked: there is nobody to
    /// wait for an answer.
    /// </summary>
    void OnClosing(object? sender, WindowClosingEventArgs e)
    {
        if (_runner.Running && e.CloseReason == WindowCloseReason.WindowClosing)
        {
            e.Cancel = true;
            if (!_closeAfterRun) AskToClose();
            return;
        }
        if (_runner.Running)
        {
            // The system is going down: the operation is asked, waited for a few seconds, then ended.
            Door.AskToStop();
            if (!_runner.WaitForExit(5000)) _runner.Kill();
        }
        SaveWindow();
        _server.Dispose();
        Paths.DropSession();
    }

    async void AskToClose()
    {
        if (_closeAsking) return;
        _closeAsking = true;
        try
        {
            var go = await Dialog.Ask(this, "Закрыть окно и остановить операцию?",
                new[]
                {
                    Lang.F("Идёт «{0}».", _runName),
                    "Операция закончит работу и закроет свои Excel и Word; книги, которые уже готовы, останутся.",
                    "Окно закроется, когда операция остановится.",
                }, "ОСТАНОВИТЬ", Tone.Danger);
            if (go is null) return;
            if (!_runner.Running) { Close(); return; }
            _closeAfterRun = true;
            StopRun(closing: true);
        }
        finally { _closeAsking = false; }
    }
}
