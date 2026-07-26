import React from "react";
import type { AssistantProduct } from "../../api/assistant";
import ProductCard from "./ProductCard";

interface AssistantMessageProps {
  role: "user" | "assistant";
  content: string;
  products?: AssistantProduct[];
}

/**
 * Parse assistant response text, splitting on **Product Name** bold markers
 * and product references. Returns an array of text segments and product cards.
 */
function parseAssistantContent(
  text: string,
  products: AssistantProduct[]
): Array<{ type: "text"; value: string } | { type: "product"; product: AssistantProduct }> {
  if (!products.length) {
    return [{ type: "text", value: text }];
  }

  const segments: Array<{ type: "text"; value: string } | { type: "product"; product: AssistantProduct }> = [];
  // Build a map of product names (lowercased) to product objects
  const productMap = new Map<string, AssistantProduct>();
  for (const p of products) {
    productMap.set(p.name.toLowerCase(), p);
  }

  // Match **Product Name** patterns
  const boldRegex = /\*\*([^*]+)\*\*/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = boldRegex.exec(text)) !== null) {
    // Add text before this match
    if (match.index > lastIndex) {
      segments.push({ type: "text", value: text.slice(lastIndex, match.index) });
    }

    const productName = match[1].trim();
    const product = productMap.get(productName.toLowerCase());

    if (product) {
      segments.push({ type: "product", product });
    } else {
      // Not a known product — keep as bold text
      segments.push({ type: "text", value: `**${productName}**` });
    }

    lastIndex = match.index + match[0].length;
  }

  // Add remaining text
  if (lastIndex < text.length) {
    segments.push({ type: "text", value: text.slice(lastIndex) });
  }

  return segments.length > 0 ? segments : [{ type: "text", value: text }];
}

const AssistantMessage: React.FC<AssistantMessageProps> = ({
  role,
  content,
  products = [],
}) => {
  const isUser = role === "user";

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-2xl rounded-br-md bg-brand-600 px-4 py-2.5 text-sm text-white">
          {content}
        </div>
      </div>
    );
  }

  const segments = parseAssistantContent(content, products);

  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] space-y-1">
        {segments.map((seg, i) => {
          if (seg.type === "product") {
            return <ProductCard key={`p-${i}`} product={seg.product} />;
          }
          // Render text with basic line-break support
          return (
            <div
              key={`t-${i}`}
              className="rounded-2xl rounded-bl-md bg-gray-100 px-4 py-2.5 text-sm text-gray-800"
            >
              {seg.value.split("\n").map((line, j) => (
                <React.Fragment key={j}>
                  {j > 0 && <br />}
                  {line}
                </React.Fragment>
              ))}
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default AssistantMessage;
