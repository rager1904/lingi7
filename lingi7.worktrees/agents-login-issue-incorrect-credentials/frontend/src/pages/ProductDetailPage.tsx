/**
 * ProductDetailPage — full product view with image gallery, add to cart
 */

import React, { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { productsApi } from "../api/resources";
import { useCartStore } from "../store";
import { formatZMW } from "../utils";
import type { Product } from "../types";

const ProductDetailPage: React.FC = () => {
  const { slug } = useParams<{ slug: string }>();
  const navigate = useNavigate();
  const addItem = useCartStore((s) => s.addItem);

  const [product, setProduct] = useState<Product | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeImageIdx, setActiveImageIdx] = useState(0);
  const [quantity, setQuantity] = useState(1);
  const [addedToCart, setAddedToCart] = useState(false);

  useEffect(() => {
    if (!slug) return;
    setIsLoading(true);
    productsApi
      .retrieve(slug)
      .then((p) => { setProduct(p); setIsLoading(false); })
      .catch(() => { setError("Product not found."); setIsLoading(false); });
  }, [slug]);

  const handleAddToCart = () => {
    if (!product) return;
    for (let i = 0; i < quantity; i++) {
      addItem({
        product_id: product.id,
        product_name: product.name,
        price_zmw: product.price_zmw,
        image_url: product.images[0]?.image_url ?? null,
        max_stock: product.stock_quantity,
      });
    }
    setAddedToCart(true);
    setTimeout(() => setAddedToCart(false), 2000);
  };

  if (isLoading) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-8 animate-pulse space-y-4">
        <div className="aspect-square rounded-xl bg-gray-200" />
        <div className="h-6 w-3/4 bg-gray-200 rounded" />
        <div className="h-8 w-1/3 bg-gray-200 rounded" />
      </div>
    );
  }

  if (error || !product) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-16 text-center">
        <p className="text-gray-500">{error ?? "Product not found."}</p>
        <button
          onClick={() => navigate(-1)}
          className="mt-4 text-sm font-medium text-emerald-600 hover:underline"
        >
          ← Go Back
        </button>
      </div>
    );
  }

  const activeImage = product.images[activeImageIdx];
  const inStock = product.stock_quantity > 0;

  return (
    <div className="mx-auto max-w-2xl px-4 py-4 space-y-4">
      {/* Back */}
      <button
        onClick={() => navigate(-1)}
        className="text-sm text-gray-500 hover:text-gray-700"
      >
        ← Back
      </button>

      {/* Primary image */}
      <div className="aspect-square overflow-hidden rounded-xl bg-gray-100">
        {activeImage ? (
          <img
            src={activeImage.image_url}
            alt={product.name}
            className="h-full w-full object-cover"
          />
        ) : (
          <div className="flex h-full items-center justify-center text-5xl text-gray-200">📦</div>
        )}
      </div>

      {/* Thumbnail strip */}
      {product.images.length > 1 && (
        <div className="flex gap-2 overflow-x-auto">
          {product.images.map((img, idx) => (
            <button
              key={img.id}
              onClick={() => setActiveImageIdx(idx)}
              className={`h-16 w-16 shrink-0 overflow-hidden rounded-lg border-2 ${
                idx === activeImageIdx ? "border-emerald-500" : "border-transparent"
              }`}
            >
              <img src={img.image_url} alt="" className="h-full w-full object-cover" />
            </button>
          ))}
        </div>
      )}

      {/* Info */}
      <div>
        <p className="text-xs text-gray-500">{product.store_name} · {product.category.name}</p>
        <h1 className="mt-1 text-xl font-bold text-gray-900">{product.name}</h1>
        <p className="mt-1 text-2xl font-black text-emerald-700">{formatZMW(product.price_zmw)}</p>
        {!inStock && <p className="mt-1 text-sm text-red-500">Out of stock</p>}
      </div>

      {/* Description */}
      <div>
        <h2 className="mb-1 text-sm font-semibold text-gray-700">Description</h2>
        <p className="text-sm text-gray-600 leading-relaxed whitespace-pre-line">
          {product.description}
        </p>
      </div>

      {/* Escrow trust badge */}
      <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">
        🔒 <strong>Buyer Protection:</strong> Your payment is held in escrow until you confirm delivery. If the item doesn't arrive or isn't as described, you can raise a dispute and get a refund.
      </div>

      {/* Quantity + Add to cart */}
      {inStock && (
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <span className="text-sm font-medium text-gray-700">Qty:</span>
            <div className="flex items-center rounded-lg border border-gray-200">
              <button
                onClick={() => setQuantity((q) => Math.max(1, q - 1))}
                className="px-3 py-1.5 text-gray-600 hover:bg-gray-50"
              >
                −
              </button>
              <span className="px-3 py-1.5 text-sm font-medium">{quantity}</span>
              <button
                onClick={() => setQuantity((q) => Math.min(product.stock_quantity, q + 1))}
                className="px-3 py-1.5 text-gray-600 hover:bg-gray-50"
              >
                +
              </button>
            </div>
            <span className="text-xs text-gray-400">{product.stock_quantity} available</span>
          </div>

          <div className="flex gap-2">
            <button
              onClick={handleAddToCart}
              className={`flex-1 rounded-xl py-3 text-sm font-semibold transition-colors ${
                addedToCart
                  ? "bg-green-600 text-white"
                  : "bg-emerald-600 text-white hover:bg-emerald-700"
              }`}
            >
              {addedToCart ? "✓ Added to Cart" : "Add to Cart"}
            </button>
            <button
              onClick={() => { handleAddToCart(); navigate("/checkout"); }}
              className="flex-1 rounded-xl border-2 border-emerald-600 py-3 text-sm font-semibold text-emerald-700 hover:bg-emerald-50"
            >
              Buy Now
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default ProductDetailPage;
