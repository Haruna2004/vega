# Meta Model API shapes (captured 2026-11-04 03:06 UTC)

Base URL: `https://api.meta.ai/v1`

## Muse Spark chat.completions (image + json_schema)

```json
{
  "id": "chatcmpl-01a1a483-4598-7516-b204-0b9e002b22b4",
  "choices": [
    {
      "finish_reason": "stop",
      "index": 0,
      "logprobs": null,
      "message": {
        "content": "{\"defects\":[\"pothole\"],\"notes\":\"A straight paved road is visible extending to the horizon with one large dark oval pothole on the left lane in the foreground.\",\"road_visible\":true}",
        "refusal": null,
        "role": "assistant",
        "annotations": null,
        "audio": null,
        "function_call": null,
        "tool_calls": null
      }
    }
  ],
  "created": 1793761428,
  "model": "muse-spark-1.3",
  "object": "chat.completion",
  "metadata": null,
  "moderation": null,
  "service_tier": null,
  "system_fingerprint": null,
  "usage": {
    "completion_tokens": 416,
    "prompt_tokens": 319,
    "total_tokens": 735,
    "completion_tokens_details": {
      "accepted_prediction_tokens": null,
      "audio_tokens": null,
      "reasoning_tokens": 367,
      "rejected_prediction_tokens": null,
      "text_tokens": null
    },
    "prompt_tokens_details": {
      "audio_tokens": null,
      "cache_write_tokens": null,
      "cached_tokens": 0,
      "image_tokens": null,
      "text_tokens": null
    }
  }
}
```

## SAM 3.1 image ('pothole')

```json
{
  "cached": true,
  "duration_s": 1.5159881114959717,
  "usage": {
    "images_processed": 1,
    "input_tokens": 0,
    "input_tokens_details": {
      "cached_tokens": 0
    },
    "output_tokens": 0,
    "output_tokens_details": {
      "reasoning_tokens": 0
    },
    "total_tokens": 0
  },
  "events_sample": [],
  "raw_text_head": "<0f>0<|box;x1=157;y1=251;x2=283;y2=273;w=640;h=360;c=0.7229437232017517|><|mask;x=0;y=0;c=0.7229437232017517;data=23,127,~!!!)A!kCl`pCSKRpy/5Uk(x%(djR]_/6mjfk.]{Lp3jUDJ*1?SluB?gI6]FhwsDyhp$XVw_9-kBM&g0*oJnLDpU=w.9YY@XD8O+bQkl.'jOsol+/oLK%#(:F6O_8$v(m[WBJn.TZ&c9+9a9%pPGMWJaK^Ez!#Z=E9o{s4mj*OM5#{9aj.d5Y%ElgpS(&l#Ux_W{O5kQr1_cr[K46bK.#^TNOvRs!%.trT3]6C[R7NCj?aazT#cCXyo0p[ERQwwb.9weVp'^aWD1wvn0h@a=iG6%xbpWVafN1fM(%lts7k[bR@K4K3?ibI@b'59$GR*b.0rgX{f%[VpOl)3]tkjg9AyG1ymVCty?ipe6/&1&&vuP{#(!'im)VWiB-k*[`.x0d)plWH-Rod+Wm'@*26v8V=?$v%:j]{'meYS`'+^6bnDXPUtuindN*-%h&I0S_eur{NPpMCMWqo)zqL0DaYG=mkjFjq[`.{O{nfiNC#1vikDxd^bQ?W1!fWDXvL2F-[k8eDN5DaGcm!a-+/MYP_TB[.jKHQU@:0x:*g#!@JW871:v/OtYA:in6{]](RbUll%f7S%g2DDN2CUAfoE`v-_7E`:@ed%EN$*bb728$XF_YEu[g6YXhr/ss_asAe]v8Kr&DAR#]Z.D-7WxCgzy]vA8-0f@=7YC`.`L`ESr9!z+eYpuhPM7{6t@gEdx&a^._sj8(Gvt26oD@v[7VefKUt(o9o=FjTMt*T2'4+m+@_2PUh.TgIdn/0%kd@yMEh_t+=)cRWtjT@/!lbWSb^Y1|>,1<|box;x1=372;y1=178;x2=419;y2=189;w=640;h=360;c=0.5241636037826538|><|mask;x=0;y=0;c=0.5241636037826538;data=12,48,~!!!%-!kDuDN=Y6ULpdFh@*)`0tDtR&mZ-jXKJnAb-iRsYS$-_-h0@a$J%9gBXUb5KAI`[SDrzAOdg?@LmJHpa?CM.uejL/qIL`hcuygAD@#EYLrDY]{V2-f9*J/pcd2=i)qgb*V5&s6[-lp]!G%1OF]kV.5WYrYk%CTx_V8lC#_1JfHcqCRLE!^!E-rbR(eqT1iV:VkJs:V.F?4p.Dic:9K#&rJopcM-(A&SAZ!%Ohd2PN.)=xUP$^0t[EXPS^dsKqxj:!ldY()EqPYrKzG.p4)I3w`GlEp=[PAYm+j`(id!%!6ld*)lLb-lz:as/4I/7NOT/Qep9LR&_-G!!|>\n",
  "n_records": 4,
  "diagnostics": []
}
```

## SAM 3.1 video ('pothole')

```json
{
  "cached": true,
  "duration_s": 5.183074712753296,
  "usage": {
    "input_tokens": 0,
    "input_tokens_details": {
      "cached_tokens": 0
    },
    "output_tokens": 0,
    "output_tokens_details": {
      "reasoning_tokens": 0
    },
    "total_tokens": 0,
    "video_frames_processed": 90
  },
  "events_sample": [],
  "raw_text_head": "<7f>0<|box;x1=339;y1=197;x2=375;y2=200;w=640;h=360;c=0.7387754917144775|><|mask;x=0;y=0;c=0.7387754917144775;data=4,37,~!!!!b!kF0XN=vpXSW(7?PGr)1B@B8gOz'7eK%C8#9f4y(22RD1]'4*[[njF3'GmS?mOQ4d6E3sC]xS.|>\n<8f>0<|box;x1=341;y1=200;x2=375;y2=204;w=640;h=360;c=0.7387754917144775|><|mask;x=0;y=0;c=0.7387754917144775;data=5,35,~!!!!m!kp.@]`RyYMt&uNKLonqY:FQN6Y{kohKG^X[ZNL!xByb/rxcUdn#7_/!6G{N7-nT%?=Y1-T#A7(dm?9kYHe1l!!!|>\n<9f>0<|box;x1=341;y1=202;x2=381;y2=206;w=640;h=360;c=0.7387754917144775|><|mask;x=0;y=0;c=0.7387754917144775;data=5,41,~!!!!t!kCn2CK3z1Gg)g[3sB6_4?jzcC=^oWO5inCD+I7+3=7(T28lX@5erq15kjmm`l4mC/k-y?a0OspF'chFuiW0HR{wH-x=j*Z!!|>\n<10f>0<|box;x1=343;y1=205;x2=383;y2=209;w=640;h=360;c=0.7387754917144775|><|mask;x=0;y=0;c=0.7387754917144775;data=5,41,~!!!!r!kF1=mk[a(3-+@`B?im8U&O9ghi84P$j]FC%BZLan$=Z]ZQaNFjv!Rs#H$(7P8uX:b_D)^^hIm3rZ:pmmPCaPI^OuQj7[-|>\n<11f>0<|box;x1=344;y1=208;x2=385;y2=212;w=640;h=360;c=0.7387754917144775|><|mask;x=0;y=0;c=0.7387754917144775;data=5,42,~!!!!p!kF0MRR%uZ.qria!noVfP)Wc2*5[t0)uSif7'IDG6phQ^8V(NR)me5l@LfIrD2{mtBpj-t@rFHK?(F=ZH^LzRuEcD'!!|>\n<12f>0<|box;x1=344;y1=212;x2=391;y2=216;w=640;h=360;c=0.7387754917144775|><|mask;x=0;y=0;c=0.7387754917144775;data=5,48,~!!!!x!kF1=rSk=RjK76N$Tdf:9@EO]WxYlF5TB:IkFyemDM0/e(2-mxdM&+m@RSOy@g$_nA=8u@AUYx`q$1vl-?v=R/b_V%+LKUlX1[!i!!|>\n<13f>0<|box;x1=346;y1=215;x2=395;y2=221;w=640;h=360;c=0.7387754917144775|><|mask;x=0;y=0;c=0.7387754917144775;data=7,50,~!!!#Z!kCmH^mA{XRc(`a$faXfGk.F-(Xti!RZi%`9tciG!8)1XSx8n{X2k:o'",
  "n_records": 176,
  "n_deltas": 67
}
```

## Muse Voice Transcribe (realtime websocket)

```json
{
  "skipped": "no audio given and espeak not installed; pass --audio"
}
```
