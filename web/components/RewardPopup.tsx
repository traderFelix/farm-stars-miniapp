"use client";

type RewardPopupProps = {
    kicker: string;
    amountLabel: string;
    description: string;
    onClose: () => void;
    buttonLabel?: string;
};

export default function RewardPopup({
    kicker,
    amountLabel,
    description,
    onClose,
    buttonLabel = "Отлично",
}: RewardPopupProps) {
    return (
        <div className="mining-popup-backdrop" onClick={onClose}>
            <div
                className="mining-popup-card mining-popup-card--success"
                onClick={(event) => event.stopPropagation()}
            >
                <div className="mining-popup-card__kicker">{kicker}</div>
                <div className="mining-popup-card__title">{amountLabel}</div>
                <div className="mining-popup-card__text">{description}</div>
                <button
                    type="button"
                    className="mining-primary-button mt-4 w-full"
                    onClick={onClose}
                >
                    {buttonLabel}
                </button>
            </div>
        </div>
    );
}
