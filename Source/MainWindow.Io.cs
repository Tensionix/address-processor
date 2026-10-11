using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.Primitives;
using Avalonia.Input;
using Avalonia.Layout;
using Avalonia.Platform.Storage;
using AudionAddressProcessor.Core;
using AudionAddressProcessor.Views;

namespace AudionAddressProcessor;

/// <summary>
/// The working folders: where an operation takes tables and documents from and where it puts the result.
/// Every start begins with input and output of the project - the last choice is not remembered.
/// A path inside the project is shown from its root; the window keeps the full one.
/// The history of paths and its pins are the file the former window kept
/// (config\path_history.json): what was pinned there is pinned here.
/// </summary>
public partial class MainWindow
{
    /// <summary>The source: a folder or one file, as a full path.</summary>
    string _source = "";
    /// <summary>The target folder, as a full path.</summary>
    string _target = "";

    PathHistory? _history;

    string DefaultSource => _manifest?.Paths.Input is { Length: > 0 } input ? input : Path.Combine(Paths.Root, "input");
    string DefaultTarget => _manifest?.Paths.Output is { Length: > 0 } output ? output : Path.Combine(Paths.Root, "output");

    void WireIo()
    {
        PickFolderButton.Click += (_, _) => PickFolder(source: true);
        PickFileButton.Click += (_, _) => PickSourceFile();
        PickTargetButton.Click += (_, _) => PickFolder(source: false);
        ResetPathsButton.Click += (_, _) => ResetPaths(quiet: false);
        ListFilesButton.Click += (_, _) => ListSourceFiles();
        SourceOpenButton.Click += (_, _) => Reveal(_source);
        // A target that is typed and not made yet is made by opening it, as the window before this one did.
        TargetOpenButton.Click += (_, _) =>
        {
            try { if (!File.Exists(_target)) Directory.CreateDirectory(_target); } catch { }
            Reveal(_target);
        };
        SourcePinButton.Click += (_, _) => TogglePin(source: true);
        TargetPinButton.Click += (_, _) => TogglePin(source: false);
        WireHistory(SourceHistoryButton, source: true);
        WireHistory(TargetHistoryButton, source: false);

        BuildClearMenu();

        // A path typed by hand is taken when the box is left or Enter is pressed.
        SourceBox.LostFocus += (_, _) => TakeTyped(source: true);
        TargetBox.LostFocus += (_, _) => TakeTyped(source: false);
        SourceBox.KeyDown += (_, e) => { if (e.Key == Key.Enter) { TakeTyped(source: true); e.Handled = true; } };
        TargetBox.KeyDown += (_, e) => { if (e.Key == Key.Enter) { TakeTyped(source: false); e.Handled = true; } };

        // A file or a folder dropped on the window becomes the source.
        DragDrop.SetAllowDrop(this, true);
        AddHandler(DragDrop.DragOverEvent, (_, e) =>
        {
            e.DragEffects = !_runner.Running && e.DataTransfer.Contains(DataFormat.File) ? DragDropEffects.Link : DragDropEffects.None;
            e.Handled = true;
        });
        AddHandler(DragDrop.DropEvent, (_, e) =>
        {
            if (_runner.Running) return;
            var path = (e.DataTransfer.TryGetFiles() ?? Array.Empty<IStorageItem>()).Select(item => item.TryGetLocalPath()).FirstOrDefault(item => item is not null);
            if (path is null) return;
            Choose(source: true, path);
            e.Handled = true;
        });
    }

    MenuItem ClearItem(string text, bool source, bool target)
    {
        var item = new MenuItem { Header = text };
        item.Click += (_, _) => ClearFolders(source, target);
        return item;
    }

    /// <summary>The folders every project has and the history of paths: made at the start, as the former window made them.</summary>
    void EnsureFolders()
    {
        if (_manifest is null) return;
        foreach (var folder in new[] { _manifest.Paths.Input, _manifest.Paths.Output, _manifest.Paths.Logs, _manifest.Paths.Report })
        {
            if (string.IsNullOrEmpty(folder)) continue;
            try { Directory.CreateDirectory(folder); }
            catch (Exception ex) { Journal.Add(Lang.F("[окно] папка не создана: {0} - {1}", folder, ex.Message)); }
        }
        var file = Path.Combine(Paths.ProjectConfig, "path_history.json");
#if DEBUG
        // A check keeps a history of its own: the paths it tries are not the owner's.
        if (Environment.GetEnvironmentVariable("AUDION_DEV_HISTORY") is { Length: > 0 } own) file = own;
#endif
        _history = new PathHistory(file);
        _history.EnsureInitial(DefaultSource, DefaultTarget);
    }

    // ------------------------------------------------------------ the two paths

    void SetSource(string path)
    {
        var before = _source;
        _source = Paths.Full(path);
        ShowPath(SourceBox, _source);
        ShowPins();
        // The lists a form shows (the headers of the first workbook) are those of the folders: they are read again.
        if (!string.Equals(before, _source, StringComparison.OrdinalIgnoreCase)) _form.SourceChanged();
    }

    void SetTarget(string path)
    {
        _target = Paths.Full(path);
        ShowPath(TargetBox, _target);
        ShowPins();
    }

    /// <summary>A path in its box, scrolled to its end: of a long path the last folder says more than the drive.</summary>
    static void ShowPath(TextBox box, string full)
    {
        box.Text = Paths.Short(full);
        box.CaretIndex = box.Text?.Length ?? 0;
    }

    /// <summary>What to clear is asked first, then the question names the paths. Built again when the language changes: a menu is not in the tree the language walks.</summary>
    void BuildClearMenu()
    {
        ClearFoldersButton.Flyout = new MenuFlyout
        {
            Placement = PlacementMode.BottomEdgeAlignedLeft,
            Items =
            {
                ClearItem("ИСТОЧНИК: удалить содержимое", source: true, target: false),
                ClearItem("НАЗНАЧЕНИЕ: удалить содержимое", source: false, target: true),
                ClearItem("ИСТОЧНИК и НАЗНАЧЕНИЕ: удалить содержимое обоих", source: true, target: true),
            },
        };
    }

    /// <summary>A path a person chose - picked, typed, dropped or taken from the history: it is set and remembered.</summary>
    void Choose(bool source, string path)
    {
        if (source) SetSource(path); else SetTarget(path);
        _history?.Remember(source, source ? _source : _target);
        ShowPins();
        var said = Lang.F(source ? "источник: {0}" : "назначение: {0}", Paths.Short(source ? _source : _target));
        Journal.Add(Lang.T("[окно] ") + said);
        Say(said, refused: false, passing: true);
    }

    /// <summary>Both paths back to input and output of the project; the history is emptied, the pins stay.</summary>
    void ResetPaths(bool quiet)
    {
        if (_runner.Running) { Say("идёт операция: пути не меняются", refused: true); return; }
        SetSource(DefaultSource);
        SetTarget(DefaultTarget);
        if (quiet) return;
        int pins = _history?.ClearKeepPins() ?? 0;
        ShowPins();
        var reset = Lang.F("источник и назначение - input и output проекта · закреплений осталось {0}", pins);
        Journal.Add(Lang.T("[окно] ") + reset);
        Say(reset, refused: false, passing: true);
    }

    /// <summary>What was typed into a path box. A source that is not on the disk is not taken: the box goes back.</summary>
    void TakeTyped(bool source)
    {
        var box = source ? SourceBox : TargetBox;
        var typed = Paths.Full(box.Text ?? "");
        var held = source ? _source : _target;
        if (typed.Length == 0 || string.Equals(typed, held, StringComparison.OrdinalIgnoreCase)) { ShowPath(box, held); return; }
        if (_runner.Running)
        {
            ShowPath(box, held);
            Say("идёт операция: пути не меняются", refused: true);
            return;
        }
        if (source && !Directory.Exists(typed) && !File.Exists(typed))
        {
            ShowPath(box, held);
            Say(Lang.F("источника нет на диске: {0}", typed), refused: true);
            return;
        }
        Choose(source, typed);
    }

    async void PickFolder(bool source)
    {
        if (_runner.Running) { Say("идёт операция: пути не меняются", refused: true); return; }
        var held = source ? _source : _target;
        IStorageFolder? from = null;
        try
        {
            var start = Directory.Exists(held) ? held : Path.GetDirectoryName(held);
            if (!string.IsNullOrEmpty(start) && Directory.Exists(start)) from = await StorageProvider.TryGetFolderFromPathAsync(start);
        }
        catch { }
        var picked = await StorageProvider.OpenFolderPickerAsync(new FolderPickerOpenOptions
        {
            Title = Lang.T(source ? "Папка-источник" : "Папка назначения"), AllowMultiple = false, SuggestedStartLocation = from,
        });
        // A run that started while the picker stood open keeps the folders it began with.
        if (_runner.Running) return;
        if (picked.Count == 0 || picked[0].TryGetLocalPath() is not { } path) { Say("выбор отменён", refused: false, passing: true); return; }
        Choose(source, path);
    }

    async void PickSourceFile()
    {
        if (_runner.Running) { Say("идёт операция: пути не меняются", refused: true); return; }
        IStorageFolder? from = null;
        try
        {
            var start = Directory.Exists(_source) ? _source : Path.GetDirectoryName(_source);
            if (!string.IsNullOrEmpty(start) && Directory.Exists(start)) from = await StorageProvider.TryGetFolderFromPathAsync(start);
        }
        catch { }
        var picked = await StorageProvider.OpenFilePickerAsync(new FilePickerOpenOptions
        {
            Title = Lang.T("Файл-источник"), AllowMultiple = false, SuggestedStartLocation = from,
            FileTypeFilter = new[]
            {
                new FilePickerFileType(Lang.T("Таблицы и документы")) { Patterns = new[] { "*.xlsx", "*.xlsm", "*.xls", "*.docx", "*.doc", "*.odt", "*.txt", "*.csv", "*.md", "*.pdf" } },
                new FilePickerFileType(Lang.T("Все файлы")) { Patterns = new[] { "*" } },
            },
        });
        if (_runner.Running) return;
        if (picked.Count == 0 || picked[0].TryGetLocalPath() is not { } path) { Say("выбор отменён", refused: false, passing: true); return; }
        Choose(source: true, path);
    }

    // ------------------------------------------------------------ the history and the pins

    void WireHistory(Button button, bool source)
    {
        var flyout = new Flyout { Placement = PlacementMode.BottomEdgeAlignedRight };
        // Built when it opens: the file may have been changed by the other window of the project.
        flyout.Opening += (_, _) => flyout.Content = HistoryList(source, flyout);
        button.Flyout = flyout;
    }

    Control HistoryList(bool source, Flyout flyout)
    {
        var rows = new StackPanel { MinWidth = 420, MaxWidth = 760 };
        var entries = _history?.Entries(source) ?? new List<HistoryEntry>();
        var held = source ? _source : _target;
        foreach (var entry in entries)
        {
            var face = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 7 };
            var pin = Icons.Sign("pin");
            pin.Opacity = entry.Pinned ? 1 : 0;
            if (entry.Pinned) pin.Classes.Add("amber");
            face.Children.Add(pin);
            face.Children.Add(new TextBlock { Text = Paths.Short(entry.Path), TextTrimming = Avalonia.Media.TextTrimming.CharacterEllipsis });
            var row = new Button { Classes = { "histrow" }, Content = face };
            bool there = Directory.Exists(entry.Path) || File.Exists(entry.Path);
            row.Classes.Set("gone", !there);
            row.Classes.Set("current", string.Equals(entry.Path, held, StringComparison.OrdinalIgnoreCase));
            ToolTip.SetTip(row, there ? entry.Path : Lang.F("нет на диске: {0}", entry.Path));
            var path = entry.Path;
            row.Click += (_, _) =>
            {
                flyout.Hide();
                if (_runner.Running) { Say("идёт операция: пути не меняются", refused: true); return; }
                if (source && !there) { Say(Lang.F("источника нет на диске: {0}", path), refused: true); return; }
                Choose(source, path);
            };
            rows.Children.Add(row);
        }
        if (entries.Count == 0) rows.Children.Add(new TextBlock { Classes = { "note" }, Text = Lang.T("история пуста"), Margin = new Thickness(8, 4) });
        return new ScrollViewer { MaxHeight = 420, HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled, Content = rows };
    }

    void TogglePin(bool source)
    {
        if (_history is null) return;
        var path = source ? _source : _target;
        bool pinned = !_history.IsPinned(source, path);
        _history.SetPinned(source, path, pinned);
        ShowPins();
        Journal.Add(Lang.T("[окно] ") + Lang.T(pinned ? "путь закреплён" : "закрепление снято") + ": " + Paths.Short(path));
        Say(Lang.T(pinned ? "путь закреплён" : "закрепление снято"), refused: false, passing: true);
    }

    /// <summary>The pin of a line is lit while its path is pinned.</summary>
    void ShowPins()
    {
        if (_history is null) return;
        SourcePinButton.Classes.Set("on", _history.IsPinned(true, _source));
        TargetPinButton.Classes.Set("on", _history.IsPinned(false, _target));
    }

    // ------------------------------------------------------------ the files

    /// <summary>The files of the source into the journal: by the alphabet, numbered, without the lock files of Word.</summary>
    void ListSourceFiles()
    {
        if (File.Exists(_source))
        {
            Journal.Show(new[] { Lang.F("[окно] источник - один файл: {0}", _source) });
            return;
        }
        if (!Directory.Exists(_source)) { Say(Lang.F("источника нет на диске: {0}", _source), refused: true); return; }
        List<string> files;
        try
        {
            files = Directory.EnumerateFiles(_source, "*", System.IO.SearchOption.AllDirectories)
                .Where(file => !Path.GetFileName(file).StartsWith("~$", StringComparison.Ordinal))
                .Select(file => Path.GetRelativePath(_source, file))
                .OrderBy(file => file, StringComparer.CurrentCultureIgnoreCase).ToList();
        }
        catch (Exception ex) { Say(Lang.F("источник не прочитан: {0}", ex.Message), refused: true); return; }
        var lines = new List<string> { Lang.F("[окно] файлов в источнике {0}: {1}", Paths.Short(_source), files.Count) };
        lines.AddRange(files.Select((file, index) => $"{index + 1,4}  {file}"));
        Journal.Show(lines);
        Say(Lang.F("файлов в источнике: {0}", files.Count), refused: false, passing: true);
    }

    /// <summary>
    /// Clearing. Everything is taken before the questions; a source outside the project is asked
    /// about on its own - another copy of it may not exist; the guards refuse the root of a drive
    /// and the project itself. What is deleted goes to the Recycle Bin.
    /// </summary>
    /// <summary>The folders are being cleared: no run starts over them, and the button stays shut.</summary>
    bool _clearing;

    async void ClearFolders(bool source, bool target)
    {
        if (_runner.Running || _finishing || _clearing) { Say(_clearing ? "идёт очистка папок" : "идёт другая операция", refused: true); return; }
        var from = _source;
        var to = _target;
        bool same = string.Equals(from, to, StringComparison.OrdinalIgnoreCase);
        var paths = new List<(bool Source, string Path)>();
        if (source) paths.Add((true, from));
        if (target && !(source && same)) paths.Add((false, to));
        foreach (var (_, path) in paths)
            if (FolderCleaner.Refusal(path) is { Length: > 0 } refusal) { Say(refusal, refused: true); return; }

        // Only a fixed local disk has a Recycle Bin; a network folder or a removable disk is cleared for good.
        const string ForGood = "Удалённое НЕ уйдёт в Корзину: папка не на локальном диске, удаление безвозвратное.";
        bool permanent = paths.Any(item => !FolderCleaner.GoesToRecycleBin(item.Path));
        if (source && !string.Equals(from, DefaultSource, StringComparison.OrdinalIgnoreCase))
        {
            bool file = File.Exists(from);
            var outside = await Dialog.Ask(this, file ? "Удалить исходный файл?" : "Очистить внешний ИСТОЧНИК?",
                new[]
                {
                    file ? "Будет удалён исходный файл. Другой копии может не существовать." : "Будут удалены все файлы и вложенные папки источника.",
                    "",
                    from,
                    "",
                    FolderCleaner.GoesToRecycleBin(from) ? "Удалённое уйдёт в Корзину." : ForGood,
                }, "УДАЛИТЬ", Tone.Danger);
            if (outside is null) return;
        }
        var lines = new List<string>();
        foreach (var (isSource, path) in paths) lines.Add(Lang.F(isSource ? "ИСТОЧНИК: {0}" : "НАЗНАЧЕНИЕ: {0}", path));
        lines.Add("");
        if (permanent) { lines.Add("Сами папки остаются."); lines.Add(ForGood); }
        else lines.Add("Сами папки остаются. Удалённое уйдёт в Корзину.");
        var go = await Dialog.Ask(this, "Удалить содержимое?", lines, "УДАЛИТЬ", Tone.Danger);
        if (go is null) return;
        // An operation started while the questions stood works with these very folders.
        if (_runner.Running || !IsVisible) { Say("идёт другая операция", refused: true); return; }

        _clearing = true;
        ClearFoldersButton.IsEnabled = false;
        var steady = _steady;
        Say("очищаю…");
        // The line goes back to what stood there before the clearing, not to "clearing".
        _steady = steady;
        try
        {
            foreach (var (isSource, path) in paths)
            {
                var done = await Task.Run(() => FolderCleaner.Clear(path));
                Journal.Add(Lang.F(isSource ? "[окно] очищен ИСТОЧНИК: {0} · удалено {1}" : "[окно] очищено НАЗНАЧЕНИЕ: {0} · удалено {1}", done.Path, done.Removed));
                if (done.Kind != "file") continue;
                // The file is gone: it leaves the history, and the path goes back to the default.
                _history?.Forget(isSource, path);
                if (isSource) SetSource(DefaultSource); else SetTarget(DefaultTarget);
            }
            Say(permanent ? "очищено: удалено безвозвратно" : "очищено: удалённое в Корзине", refused: false, passing: true);
        }
        catch (Exception ex)
        {
            Say(Lang.F("очистка не вышла: {0}", ex.Message), refused: true);
        }
        finally
        {
            _clearing = false;
            ClearFoldersButton.IsEnabled = !_runner.Running && !_finishing;
            _form.SourceChanged();
        }
    }
}
