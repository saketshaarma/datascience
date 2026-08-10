import { useState } from "react";
import { Copy, Check, Download } from "lucide-react";
import { toast } from "sonner";

const escapeHtml = (s) =>
  s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

function highlightHcl(code) {
  let html = escapeHtml(code);
  html = html.replace(/(&quot;[^&]*?&quot;|"[^"]*?")/g, '<span class="tf-string">$1</span>');
  html = html.replace(/\b(resource|provider|variable|terraform|required_providers|ingress|tags|type|default|source|version)\b(?![^<]*<\/span>)/g,
    '<span class="tf-key">$1</span>');
  html = html.replace(/\b(\d+)\b/g, '<span class="tf-num">$1</span>');
  return html;
}

function highlightJson(code) {
  let html = escapeHtml(code);
  html = html.replace(/(&quot;(?:[^&]|&(?!quot;))*?&quot;)(\s*:)/g, '<span class="tf-key">$1</span>$2');
  html = html.replace(/(:\s*)(&quot;(?:[^&]|&(?!quot;))*?&quot;)/g, '$1<span class="tf-string">$2</span>');
  html = html.replace(/(:\s*)(\d+)/g, '$1<span class="tf-num">$2</span>');
  return html;
}

export const CodeBlock = ({ code, language, filename }) => {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    await navigator.clipboard.writeText(code);
    setCopied(true);
    toast.success("Copied to clipboard");
    setTimeout(() => setCopied(false), 1500);
  };

  const download = () => {
    const blob = new Blob([code], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
    toast.success(`Downloaded ${filename}`);
  };

  const html = language === "json" ? highlightJson(code) : highlightHcl(code);

  return (
    <div className="relative rounded-sm border border-[#27272A] bg-[#050506] overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2 border-b border-[#27272A] bg-[#0d0d0f]">
        <span className="font-mono text-xs text-zinc-500">{filename}</span>
        <div className="flex items-center gap-1">
          <button data-testid={`download-${language}`} onClick={download} className="p-1.5 rounded-sm text-zinc-500 hover:text-white hover:bg-white/10 transition-colors duration-150">
            <Download className="h-4 w-4" />
          </button>
          <button data-testid={`copy-${language}`} onClick={copy} className="p-1.5 rounded-sm text-zinc-500 hover:text-white hover:bg-white/10 transition-colors duration-150">
            {copied ? <Check className="h-4 w-4 text-green-400" /> : <Copy className="h-4 w-4" />}
          </button>
        </div>
      </div>
      <pre className="p-4 overflow-auto max-h-[60vh] text-xs leading-relaxed">
        <code dangerouslySetInnerHTML={{ __html: html }} />
      </pre>
    </div>
  );
};
