import { useState } from 'react';
import { X, CreditCard, ShieldCheck, CheckCircle2 } from 'lucide-react';
import { api } from '../api';

interface BookingModalProps {
  itemName: string;
  priceDisplay: string; // Changed from amount: number
  onClose: () => void;
}

export const BookingModal = ({ itemName, priceDisplay, onClose }: BookingModalProps) => {
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [confCode, setConfCode] = useState('');

  const handlePayment = async () => {
    setLoading(true);
    try {
      // Extract numeric value for the mock backend record
      const numericAmount = parseFloat(priceDisplay.replace(/[^0-9.]/g, '')) || 0;

      const res = await api.post('/bookings/confirm', {
        booking_type: 'hotel',
        item_name: itemName,
        amount: numericAmount,
        details: { source: 'Warik AI Chat', original_price: priceDisplay }
      });
      setConfCode(res.data.confirmation_code);
      setSuccess(true);
    } catch (e) {
      alert("Payment failed. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="bg-jcard border border-jprimary/30 rounded-2xl w-full max-w-md overflow-hidden shadow-2xl">

        {!success ? (
          <>
            <div className="flex justify-between items-center p-4 border-b border-jmuted/20 bg-jbg/50">
              <h3 className="font-bold text-white flex items-center gap-2"><CreditCard size={18} /> Secure Checkout</h3>
              <button onClick={onClose} className="text-jmuted hover:text-white"><X size={20} /></button>
            </div>

            <div className="p-6">
              <div className="mb-6">
                <p className="text-xs text-jmuted uppercase tracking-wider mb-1">Booking</p>
                <p className="text-white font-bold text-lg">{itemName}</p>
              </div>

              <div className="bg-jbg rounded-xl p-4 mb-6 border border-jmuted/20">
                <div className="flex justify-between text-sm mb-2 text-jmuted">
                  <span>Base Fare</span>
                  <span>{priceDisplay}</span>
                </div>
                <div className="flex justify-between text-sm mb-2 text-jmuted">
                  <span>Taxes & Fees</span>
                  <span>Included</span>
                </div>
                <div className="border-t border-jmuted/20 my-2 pt-2 flex justify-between font-bold text-white">
                  <span>Total to Pay</span>
                  <span className="text-jsecondary">{priceDisplay}</span>
                </div>
              </div>

              <div className="flex items-center gap-2 text-xs text-green-400 mb-6 bg-green-400/10 p-3 rounded-lg">
                <ShieldCheck size={16} />
                <span>Payments are secure and encrypted.</span>
              </div>

              <button
                onClick={handlePayment}
                disabled={loading}
                className="w-full bg-jprimary hover:bg-jsecondary text-white font-bold py-3 rounded-xl transition-all disabled:opacity-50 flex justify-center items-center gap-2"
              >
                {loading ? 'Processing...' : `Pay ${priceDisplay}`}
              </button>
            </div>
          </>
        ) : (
          <div className="p-8 text-center flex flex-col items-center">
            <CheckCircle2 size={64} className="text-green-400 mb-4" />
            <h3 className="text-2xl font-bold text-white mb-2">Booking Confirmed!</h3>
            <p className="text-jmuted text-sm mb-4">Your payment was successful.</p>

            <div className="bg-jbg border border-jprimary/30 rounded-xl p-4 w-full mb-6">
              <p className="text-xs text-jmuted mb-1">Confirmation Code</p>
              <p className="font-mono text-lg text-jsecondary font-bold">{confCode}</p>
            </div>

            <button
              onClick={onClose}
              className="w-full bg-jmuted/20 hover:bg-jmuted/30 text-white font-bold py-3 rounded-xl transition-all"
            >
              Done
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
