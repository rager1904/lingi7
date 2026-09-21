/** Animated L7 brand mark: plays the full reveal film, no companion wordmark. */
export default function BrandLogo() {
  return <span className="grid aspect-video h-10 overflow-hidden rounded-xl bg-[#070e1b]">
    <video autoPlay muted loop playsInline disablePictureInPicture aria-hidden="true" tabIndex={-1}
      poster="/brand/l7-poster.svg" className="h-full w-full object-cover">
      <source src="/brand/lingi7-reveal.webm" type="video/webm" />
    </video>
  </span>;
}