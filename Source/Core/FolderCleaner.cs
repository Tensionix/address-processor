using System;
using System.IO;
using System.Linq;
using Microsoft.VisualBasic.FileIO;

namespace AudionAddressProcessor.Core;

/// <summary>What clearing a path of the working folders did.</summary>
public sealed record Cleared(string Path, string Kind, int Removed);

/// <summary>
/// Clearing the working folders: the contents of a folder go, the folder stays; a source that is
/// one file goes itself. The guards are those of the window before this one (NiceGUI, removed on
/// 11.10.2026; its delete_workspace_path_contents):
///   - the root of a drive and the root of the project are never cleared;
///   - a link to a folder is taken off, not walked through - what it points at is not touched.
/// One thing is done otherwise: what is deleted goes to the Recycle Bin, not past it.
/// </summary>
public static class FolderCleaner
{
    /// <summary>Why a path may not be cleared; "" when it may.</summary>
    public static string Refusal(string path)
    {
        string full;
        try { full = Path.GetFullPath(path); } catch { return Lang.F("путь не разобран: {0}", path); }
        var trimmed = full.TrimEnd('\\', '/');
        if (Path.GetPathRoot(full) is { } drive && string.Equals(drive.TrimEnd('\\', '/'), trimmed, StringComparison.OrdinalIgnoreCase))
            return Lang.F("корень диска не очищается: {0}", full);
        if (string.Equals(trimmed, Paths.Root, StringComparison.OrdinalIgnoreCase))
            return Lang.F("корень проекта не очищается: {0}", full);
        // The project must not be cleared from above either: a folder that holds it.
        if ((Paths.Root + "\\").StartsWith(trimmed + "\\", StringComparison.OrdinalIgnoreCase))
            return Lang.F("в этой папке лежит сам проект, она не очищается: {0}", full);
        return "";
    }

    /// <summary>
    /// A symbolic link or a junction. Not every reparse point: the files a cloud keeps "on demand" carry
    /// the attribute without being links, and they are to be deleted like any other file.
    /// </summary>
    static bool IsLink(FileSystemInfo item) => item.LinkTarget is not null;

    /// <summary>
    /// Does what is deleted from this path go to the Recycle Bin? Only on a fixed local disk: a network
    /// folder and a removable disk have none, and the shell deletes there for good, without a question.
    /// </summary>
    public static bool GoesToRecycleBin(string path)
    {
        try
        {
            var full = Path.GetFullPath(path);
            if (full.StartsWith(@"\\", StringComparison.Ordinal)) return false;
            return Path.GetPathRoot(full) is { Length: > 0 } drive && new DriveInfo(drive).DriveType == DriveType.Fixed;
        }
        catch { return false; }
    }

    /// <summary>One item to the Recycle Bin; a link is taken off where it stands.</summary>
    static void Remove(FileSystemInfo item)
    {
        if (IsLink(item))
        {
            // Deleting a link deletes the link: Directory.Delete without "recursive" does not go inside.
            if (item is DirectoryInfo) Directory.Delete(item.FullName, false);
            else File.Delete(item.FullName);
            return;
        }
        if (item is DirectoryInfo)
            FileSystem.DeleteDirectory(item.FullName, UIOption.OnlyErrorDialogs, RecycleOption.SendToRecycleBin, UICancelOption.ThrowException);
        else
            FileSystem.DeleteFile(item.FullName, UIOption.OnlyErrorDialogs, RecycleOption.SendToRecycleBin, UICancelOption.ThrowException);
    }

    /// <summary>
    /// Clears a path. Kind: "missing" - nothing there; "file" - the path was a file or a link and
    /// is gone itself; "folder" - its contents are gone. Throws when the guards refuse.
    /// </summary>
    public static Cleared Clear(string path)
    {
        if (Refusal(path) is { Length: > 0 } refusal) throw new InvalidOperationException(refusal);
        var full = Path.GetFullPath(path);
        if (File.Exists(full))
        {
            Remove(new FileInfo(full));
            return new Cleared(full, "file", 1);
        }
        if (!Directory.Exists(full)) return new Cleared(full, "missing", 0);
        var folder = new DirectoryInfo(full);
        if (IsLink(folder))
        {
            Remove(folder);
            return new Cleared(full, "file", 1);
        }
        int removed = 0;
        foreach (var child in folder.EnumerateFileSystemInfos().OrderBy(item => item.Name, StringComparer.OrdinalIgnoreCase).ToList())
        {
            Remove(child);
            removed++;
        }
        return new Cleared(full, "folder", removed);
    }
}
