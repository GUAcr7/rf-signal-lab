#define iio_buffer_refill p39_original_refill
#include "mock_rx_full_p36.c"
#undef iio_buffer_refill
ssize_t iio_buffer_refill(struct iio_buffer *b) {
    delay_ms(2);
    return p39_original_refill(b);
}
