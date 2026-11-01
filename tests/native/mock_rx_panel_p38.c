/* The periodic monitor takes only one buffer per context. Inject cancellation
 * in that first refill; the P36 fixture waits until its fourth refill. */
#define iio_buffer_refill p38_original_refill
#include "mock_rx_full_p36.c"
#undef iio_buffer_refill
ssize_t iio_buffer_refill(struct iio_buffer *b) {
    if (fault("cancel")) {
        raise(SIGTERM);
        while (!atomic_load(&b->canceled)) delay_ms(1);
        return -ECANCELED;
    }
    return p38_original_refill(b);
}
