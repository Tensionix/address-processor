using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text.Json;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Input;
using Avalonia.Layout;
using Avalonia.Media;
using AudionAddressProcessor.Core;

namespace AudionAddressProcessor.Views;

/// <summary>
/// The summary of a report in a window of its own: the rows of <see cref="ReportSummary"/>, the
/// path of the file, a way to open it, and the JSON itself under a fold. The report is read when the
/// window is made and not kept: it is the file an operation wrote.
/// </summary>
public static class ReportView
{
    public static void Show(Window owner, string path)
    {
        JsonDocument? document = null;
        string raw = "";
        try
        {
            raw = File.ReadAllText(path);
            document = JsonDocument.Parse(raw);
        }
        catch (Exception ex)
        {
            Journal.Add(Lang.F("[окно] отчёт не прочитан: {0}", ex.Message));
            try { Process.Start(new ProcessStartInfo(path) { UseShellExecute = true }); } catch { }
            return;
        }
        using (document)
        {
            var window = new Window
            {
                Title = Lang.T("Сводка отчёта"), Width = 760, SizeToContent = SizeToContent.Height, MaxHeight = 760,
                WindowStartupLocation = WindowStartupLocation.CenterOwner, CanResize = false, ShowInTaskbar = false,
                Background = App.Ink("AppBg"), Foreground = App.Ink("TextMain"),
                FontFamily = (FontFamily?)(Application.Current?.FindResource("FontUi")) ?? FontFamily.Default,
                FontSize = 13,
            };
            var rows = new StackPanel { Spacing = 3 };
            var grid = new Grid { ColumnDefinitions = new ColumnDefinitions("Auto,*"), RowDefinitions = new RowDefinitions() };
            int row = 0;
            foreach (var (key, value) in ReportSummary.Rows(document.RootElement, Path.GetFileName(path)))
            {
                grid.RowDefinitions.Add(new RowDefinition(GridLength.Auto));
                var name = new TextBlock { Text = key, Foreground = App.Ink("CrumbInk"), Margin = new Thickness(0, 1, 18, 1), FontFamily = (FontFamily?)(Application.Current?.FindResource("FontGrid")) ?? FontFamily.Default };
                var text = new SelectableTextBlock { Text = value, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 1) };
                Grid.SetRow(name, row);
                Grid.SetRow(text, row);
                Grid.SetColumn(text, 1);
                grid.Children.Add(name);
                grid.Children.Add(text);
                row++;
            }
            rows.Children.Add(grid);

            var json = new TextBox
            {
                Text = raw.Length > 20000 ? raw[..20000] : raw, IsReadOnly = true, AcceptsReturn = true, TextWrapping = TextWrapping.NoWrap, MaxHeight = 280,
                FontFamily = (FontFamily?)(Application.Current?.FindResource("FontGrid")) ?? FontFamily.Default, FontSize = 11,
            };
            var fold = new Expander { Header = Lang.T("JSON отчёта"), Margin = new Thickness(0, 12, 0, 0), Content = json };

            var open = new Button { Content = Lang.T("ОТКРЫТЬ ФАЙЛ"), MinWidth = 140, MinHeight = 30, Margin = new Thickness(0, 0, 9, 0) };
            open.Click += (_, _) => { try { Process.Start(new ProcessStartInfo(path) { UseShellExecute = true }); } catch { } };
            var close = new Button { Content = Lang.T("ЗАКРЫТЬ"), MinWidth = 118, MinHeight = 30, IsCancel = true, IsDefault = true };
            close.Click += (_, _) => window.Close();

            window.Content = new Border
            {
                Background = App.Ink("PanelBg"), BorderBrush = App.Ink("BorderSoft"), BorderThickness = new Thickness(1), CornerRadius = new CornerRadius(8),
                Margin = new Thickness(10), Padding = new Thickness(18, 15),
                Child = new StackPanel
                {
                    Children =
                    {
                        new TextBlock { Text = Lang.T("Сводка отчёта"), FontSize = 15, FontWeight = FontWeight.SemiBold, Margin = new Thickness(0, 0, 0, 4) },
                        new TextBlock { Text = path, Foreground = App.Ink("CrumbInk"), FontSize = 11, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 0, 0, 12) },
                        new ScrollViewer { MaxHeight = 360, HorizontalScrollBarVisibility = Avalonia.Controls.Primitives.ScrollBarVisibility.Disabled, Content = rows },
                        fold,
                        new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right, Margin = new Thickness(0, 16, 0, 0), Children = { open, close } },
                    },
                },
            };
            window.ShowDialog(owner);
        }
    }
}
