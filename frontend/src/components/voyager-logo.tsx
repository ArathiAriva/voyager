import Image from "next/image";
import horizonIcon from "../../public/voyager-horizon-icon.png";

export function VoyagerLogo({ size = 36, decorative = false }: { size?: number; decorative?: boolean }) {
  return (
    <Image
      src={horizonIcon}
      alt={decorative ? "" : "Voyager"}
      width={size}
      height={size}
      priority
      style={{ width: size, height: size, borderRadius: size / 4, flexShrink: 0 }}
    />
  );
}
