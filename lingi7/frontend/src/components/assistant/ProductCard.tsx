import React from "react";
import { useNavigate } from "react-router-dom";
import type { AssistantProduct } from "../../api/assistant";

interface ProductCardProps {
  product: AssistantProduct;
}

const ProductCard: React.FC<ProductCardProps> = ({ product }) => {
  const navigate = useNavigate();

  const handleClick = () => {
    if (product.pk && !isNaN(Number(product.pk))) {
      navigate(`/products/${product.pk}`);
    }
  };

  const priceNum = parseFloat(product.price);
  const displayPrice = isNaN(priceNum)
    ? product.price
    : `K ${priceNum.toLocaleString("en-ZM", { minimumFractionDigits: 2 })}`;

  return (
    <button
      type="button"
      onClick={handleClick}
      className="mt-2 flex w-full items-center gap-3 rounded-xl border border-gray-100 bg-gray-50 p-2.5 text-left transition hover:border-brand-200 hover:bg-brand-50"
    >
      {product.image ? (
        <img
          src={product.image}
          alt={product.name}
          className="h-14 w-14 flex-shrink-0 rounded-lg object-cover"
          loading="lazy"
        />
      ) : (
        <div className="flex h-14 w-14 flex-shrink-0 items-center justify-center rounded-lg bg-gray-200 text-xs text-gray-400">
          No img
        </div>
      )}
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-semibold text-gray-900">
          {product.name}
        </p>
        <p className="mt-0.5 text-sm font-bold text-brand-600">{displayPrice}</p>
      </div>
    </button>
  );
};

export default ProductCard;
