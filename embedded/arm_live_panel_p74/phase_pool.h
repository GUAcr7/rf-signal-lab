/* Fixed C8 group mean. Frozen CNN weights, quantizer and preprocess retained.
 * Requires original[], logits[] and infer() from trained_cnn_infer.c.
 * Restores original input; no known class/source or confidence fallback.
 */
static int p74_infer(int quantized) {
    static const double c[8]={1,.70710678118654752440,0,-.70710678118654752440,
                             -1,-.70710678118654752440,0,.70710678118654752440};
    static const double s[8]={0,.70710678118654752440,1,.70710678118654752440,
                             0,-.70710678118654752440,-1,-.70710678118654752440};
    float input[2048];double pooled_logits[3]={0,0,0};
    memcpy(input,original,sizeof input);
    for(int phase=0;phase<8;phase++) {
        for(int n=0;n<1024;n++) {
            double i=input[2*n],q=input[2*n+1];
            original[2*n]=(float)(i*c[phase]-q*s[phase]);
            original[2*n+1]=(float)(i*s[phase]+q*c[phase]);
        }
        if(infer(quantized)) {
            memcpy(original,input,sizeof input);return 1;
        }
        for(int k=0;k<3;k++)pooled_logits[k]+=logits[k]/8.0;
    }
    memcpy(original,input,sizeof input);
    memcpy(logits,pooled_logits,sizeof pooled_logits);
    return 0;
}
