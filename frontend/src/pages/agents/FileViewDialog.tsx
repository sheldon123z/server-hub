import React, { useState, useCallback } from "react";
import { FileText, Copy, Download, Edit, Save, X, Loader2 } from "lucide-react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import toast from "react-hot-toast";
import { cn } from "@/lib/utils";
import { getLanguage, isMarkdown } from "@/lib/file-utils";
import { MarkdownContent } from "./MarkdownContent";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------
interface FileViewDialogProps {
  fileName: string;
  content: string;
  onClose: () => void;
  onSave?: (fileName: string, content: string) => Promise<void>;
}

// ---------------------------------------------------------------------------
// FileViewDialog
// ---------------------------------------------------------------------------
export const FileViewDialog = React.memo<FileViewDialogProps>(
  function FileViewDialog({ fileName, content, onClose, onSave }) {
    const [isEditing, setIsEditing] = useState(false);
    const [editValue, setEditValue] = useState(content);
    const [isSaving, setIsSaving] = useState(false);

    const language = getLanguage(fileName);
    const showMarkdown = isMarkdown(fileName) && !isEditing;

    // -----------------------------------------------------------------------
    // Handlers
    // -----------------------------------------------------------------------
    const handleCopy = useCallback(() => {
      navigator.clipboard
        .writeText(content)
        .then(() => toast.success("已复制"))
        .catch(() => toast.error("复制失败"));
    }, [content]);

    const handleDownload = useCallback(() => {
      const blob = new Blob([content], { type: "text/plain" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = fileName.split("/").pop() ?? fileName;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }, [content, fileName]);

    const handleEdit = useCallback(() => {
      setEditValue(content);
      setIsEditing(true);
    }, [content]);

    const handleCancel = useCallback(() => {
      setIsEditing(false);
      setEditValue(content);
    }, [content]);

    const handleSave = useCallback(async () => {
      if (!onSave) return;
      setIsSaving(true);
      try {
        await onSave(fileName, editValue);
        setIsEditing(false);
        toast.success("已保存");
      } catch {
        toast.error("保存失败");
      } finally {
        setIsSaving(false);
      }
    }, [onSave, fileName, editValue]);

    const handleOverlayClick = useCallback(() => {
      if (!isEditing) onClose();
    }, [isEditing, onClose]);

    const stopPropagation = useCallback(
      (e: React.MouseEvent) => e.stopPropagation(),
      []
    );

    // -----------------------------------------------------------------------
    // Render
    // -----------------------------------------------------------------------
    return (
      <div
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
        onClick={handleOverlayClick}
      >
        <div
          className="relative mx-4 flex w-full max-w-4xl flex-col rounded-lg border border-border bg-card"
          style={{ maxHeight: "80vh" }}
          onClick={stopPropagation}
        >
          {/* ----------------------------------------------------------------
              Header
          ---------------------------------------------------------------- */}
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            {/* Left: icon + filename */}
            <div className="flex min-w-0 items-center gap-2">
              <FileText
                size={16}
                className="shrink-0 text-text2"
                aria-hidden="true"
              />
              <span
                className="truncate font-medium text-text"
                title={fileName}
              >
                {fileName.split("/").pop() ?? fileName}
              </span>
            </div>

            {/* Right: action buttons + close */}
            <div className="ml-3 flex shrink-0 items-center gap-1">
              {/* Edit — only if onSave provided and not already editing */}
              {onSave && !isEditing && (
                <button
                  onClick={handleEdit}
                  className="flex items-center gap-1 rounded px-2 py-1 text-xs text-text2 transition-colors hover:bg-bg2 hover:text-text"
                  title="编辑"
                >
                  <Edit size={13} />
                  <span>编辑</span>
                </button>
              )}

              {/* Copy */}
              <button
                onClick={handleCopy}
                className="flex items-center gap-1 rounded px-2 py-1 text-xs text-text2 transition-colors hover:bg-bg2 hover:text-text"
                title="复制"
              >
                <Copy size={13} />
                <span>复制</span>
              </button>

              {/* Download */}
              <button
                onClick={handleDownload}
                className="flex items-center gap-1 rounded px-2 py-1 text-xs text-text2 transition-colors hover:bg-bg2 hover:text-text"
                title="下载"
              >
                <Download size={13} />
                <span>下载</span>
              </button>

              {/* Close */}
              <button
                onClick={onClose}
                className="ml-1 rounded p-1 text-text2 transition-colors hover:bg-bg2 hover:text-text"
                title="关闭"
              >
                <X size={15} />
              </button>
            </div>
          </div>

          {/* ----------------------------------------------------------------
              Body
          ---------------------------------------------------------------- */}
          <div className="min-h-0 flex-1 overflow-auto">
            {content.trim() === "" ? (
              <div className="flex h-32 items-center justify-center text-sm text-text2">
                文件为空
              </div>
            ) : isEditing ? (
              /* Edit textarea */
              <textarea
                className={cn(
                  "h-full min-h-[400px] w-full resize-none bg-bg p-4",
                  "border-0 font-mono text-sm text-text outline-none",
                  "placeholder:text-text2"
                )}
                value={editValue}
                onChange={(e) => setEditValue(e.target.value)}
                spellCheck={false}
                autoFocus
              />
            ) : showMarkdown ? (
              /* Markdown view */
              <div className="p-5">
                <MarkdownContent content={content} />
              </div>
            ) : (
              /* Syntax-highlighted view */
              <SyntaxHighlighter
                language={language}
                style={oneDark}
                showLineNumbers
                wrapLines
                customStyle={{
                  margin: 0,
                  borderRadius: 0,
                  fontSize: "0.85em",
                  background: "transparent",
                  padding: "1.25rem",
                }}
              >
                {content}
              </SyntaxHighlighter>
            )}
          </div>

          {/* ----------------------------------------------------------------
              Footer — only visible in edit mode
          ---------------------------------------------------------------- */}
          {isEditing && (
            <div className="flex items-center justify-end gap-2 border-t border-border px-4 py-3">
              <button
                onClick={handleCancel}
                disabled={isSaving}
                className={cn(
                  "rounded border border-border bg-bg2 px-3 py-1.5 text-sm text-text2",
                  "transition-colors hover:bg-bg hover:text-text",
                  "disabled:cursor-not-allowed disabled:opacity-50"
                )}
              >
                取消
              </button>
              <button
                onClick={handleSave}
                disabled={isSaving}
                className={cn(
                  "flex items-center gap-1.5 rounded bg-accent px-3 py-1.5 text-sm font-medium text-[#0f172a]",
                  "transition-opacity hover:opacity-90",
                  "disabled:cursor-not-allowed disabled:opacity-50"
                )}
              >
                {isSaving ? (
                  <Loader2 size={13} className="animate-spin" />
                ) : (
                  <Save size={13} />
                )}
                保存
              </button>
            </div>
          )}
        </div>
      </div>
    );
  }
);
