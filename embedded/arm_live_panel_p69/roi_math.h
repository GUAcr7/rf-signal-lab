/* Explicit non-wrapping, known single-source ROI; NOT a general detector.
 * Bin powers are count^2/bin. No noise subtraction or guessed RF calibration.
 */
#ifndef P69_ROI_MATH_H
#define P69_ROI_MATH_H
#include <math.h>
#include <string.h>
enum p69_status {P69_OK,P69_INVALID,P69_CAL_REQUIRED,P69_NO_SIGNAL,
    P69_CLIPPED,P69_STOPPED,P69_WEAK,P69_EDGE,P69_OUTSIDE};
static const char *p69_names[]={"VALID","INVALID_INPUT","CALIBRATION_REQUIRED",
    "NO_USABLE_SIGNAL","CLIPPED","STOPPED","BELOW_BACKGROUND_GATE",
    "ROI_EDGE_OR_BROAD","DOMINANT_PEAK_OUTSIDE_ROI"};
struct p69_result {
    enum p69_status status;
    double lower,upper,midpoint,rf,width,power,background,ratio;
};
static struct p69_result p69_compute(const double *bins,const double *background,
        int count,double fs,double lo,double center,int allowed) {
    struct p69_result out={.status=P69_INVALID};
    if(count!=1024||!isfinite(fs)||fs!=30720000||!isfinite(lo)||lo<=0
        ||!isfinite(center)||fabs(center)>fs/2-600000)return out;
    if(!allowed){out.status=P69_NO_SIGNAL;return out;}
    double df=fs/count,low=center-600000,high=center+600000;
    double masses[1024],left[1024],right[1024];
    int maximum_index=0;double maximum=-1;
    for(int k=0;k<count;k++) {
        int source=(k+count/2)%count;double p=bins[source],b=background[source];
        if(!isfinite(p)||p<0||!isfinite(b)||b<0)return out;
        double f=(k-count/2)*df;
        if(p>maximum){maximum=p;maximum_index=k;}
        left[k]=fmax(f-df/2,low);right[k]=fmin(f+df/2,high);
        double overlap=fmax(0,right[k]-left[k]);masses[k]=p*overlap/df;
        out.power+=masses[k];out.background+=b*overlap/df;
    }
    if(!(out.power>0)||!(out.background>0)){out.status=P69_WEAK;return out;}
    out.ratio=out.power/out.background;
    if(!isfinite(out.ratio)||out.ratio<10){out.status=P69_WEAK;return out;}
    double peak=(maximum_index-count/2)*df;
    if(peak<low||peak>high){out.status=P69_OUTSIDE;return out;}
    double cumulative=0,quantiles[2]={0,0};int found=0;
    for(int k=0;k<count;k++) {
        if(masses[k]>0)while(found<2) {
            double goal=out.power*(found?.995:.005);
            if(cumulative+masses[k]<goal)break;
            quantiles[found]=left[k]+(goal-cumulative)/masses[k]*(right[k]-left[k]);found++;
        }
        cumulative+=masses[k];
    }
    if(found!=2)return out;
    if(quantiles[0]<low+df||quantiles[1]>high-df){out.status=P69_EDGE;return out;}
    out.lower=quantiles[0];out.upper=quantiles[1];out.width=out.upper-out.lower;
    out.midpoint=(out.lower+out.upper)/2;out.rf=lo+out.midpoint;out.status=P69_OK;
    return out;
}
#endif
