import zipfile, glob, subprocess, torch, os, traceback, sys, warnings, shutil, numpy as np
from mega import Mega
os.environ["no_proxy"] = "localhost, 127.0.0.1, ::1"
import threading
from time import sleep
from subprocess import Popen
import faiss
from random import shuffle
import json, datetime, requests
from gtts import gTTS
now_dir = os.getcwd()
sys.path.append(now_dir)
tmp = os.path.join(now_dir, "TEMP")
shutil.rmtree(tmp, ignore_errors=True)
shutil.rmtree("%s/runtime/Lib/site-packages/infer_pack" % (now_dir), ignore_errors=True)
shutil.rmtree("%s/runtime/Lib/site-packages/uvr5_pack" % (now_dir), ignore_errors=True)
os.makedirs(tmp, exist_ok=True)
os.makedirs(os.path.join(now_dir, "logs"), exist_ok=True)
os.makedirs(os.path.join(now_dir, "weights"), exist_ok=True)
os.environ["TEMP"] = tmp
warnings.filterwarnings("ignore")
torch.manual_seed(114514)
from i18n import I18nAuto
import ffmpeg
#from MDXNet import MDXNetDereverb

i18n = I18nAuto()
#i18n.print()
# Determine se existe um cartão N que pode ser usado para treinamento e raciocínio acelerado
ngpu = torch.cuda.device_count()
gpu_infos = []
mem = []
if (not torch.cuda.is_available()) or ngpu == 0:
    if_gpu_ok = False
else:
    if_gpu_ok = False
    for i in range(ngpu):
        gpu_name = torch.cuda.get_device_name(i)
        if (
            "10" in gpu_name
            or "16" in gpu_name
            or "20" in gpu_name
            or "30" in gpu_name
            or "40" in gpu_name
            or "A2" in gpu_name.upper()
            or "A3" in gpu_name.upper()
            or "A4" in gpu_name.upper()
            or "P4" in gpu_name.upper()
            or "A50" in gpu_name.upper()
            or "A60" in gpu_name.upper()
            or "70" in gpu_name
            or "80" in gpu_name
            or "90" in gpu_name
            or "M4" in gpu_name.upper()
            or "T4" in gpu_name.upper()
            or "TITAN" in gpu_name.upper()
        ):  # A10#A100#V100#A40#P40#M40#K80#A4500
            if_gpu_ok = True  # 至少有一张能用的N卡
            gpu_infos.append("%s\t%s" % (i, gpu_name))
            mem.append(
                int(
                    torch.cuda.get_device_properties(i).total_memory
                    / 1024
                    / 1024
                    / 1024
                    + 0.4
                )
            )
if if_gpu_ok == True and len(gpu_infos) > 0:
    gpu_info = "\n".join(gpu_infos)
    default_batch_size = min(mem) // 2
else:
    gpu_info = i18n("Seu Colab não esta conectado a uma GPU, tente novamente ou entre com outra conta.")
    default_batch_size = 1
gpus = "-".join([i[0] for i in gpu_infos])
from infer_pack.models import (
    SynthesizerTrnMs256NSFsid,
    SynthesizerTrnMs256NSFsid_nono,
    SynthesizerTrnMs768NSFsid,
    SynthesizerTrnMs768NSFsid_nono,
)
import soundfile as sf
from fairseq import checkpoint_utils
import gradio as gr
import logging
from vc_infer_pipeline import VC
from config import Config
from infer_uvr5 import _audio_pre_, _audio_pre_new
from my_utils import load_audio
from train.process_ckpt import show_info, change_info, merge, extract_small_model

config = Config()
# from trainset_preprocess_pipeline import PreProcess
logging.getLogger("numba").setLevel(logging.WARNING)

hubert_model = None

def load_hubert():
    global hubert_model
    models, _, _ = checkpoint_utils.load_model_ensemble_and_task(
        ["hubert_base.pt"],
        suffix="",
    )
    hubert_model = models[0]
    hubert_model = hubert_model.to(config.device)
    if config.is_half:
        hubert_model = hubert_model.half()
    else:
        hubert_model = hubert_model.float()
    hubert_model.eval()


weight_root = "weights"
weight_uvr5_root = "uvr5_weights"
index_root = "logs"
names = []
for name in os.listdir(weight_root):
    if name.endswith(".pth"):
        names.append(name)
index_paths = []
for root, dirs, files in os.walk(index_root, topdown=False):
    for name in files:
        if name.endswith(".index") and "trained" not in name:
            index_paths.append("%s/%s" % (root, name))
uvr5_names = []
for name in os.listdir(weight_uvr5_root):
    if name.endswith(".pth") or "onnx" in name:
        uvr5_names.append(name.replace(".pth", ""))


def vc_single(
    sid,
    input_audio_path,
    f0_up_key,
    f0_file,
    f0_method,
    file_index,
    #file_index2,
    # file_big_npy,
    index_rate,
    filter_radius,
    resample_sr,
    rms_mix_rate,
    protect,
    crepe_hop_length,
):  # spk_item, input_audio0, vc_transform0,f0_file,f0method0
    global tgt_sr, net_g, vc, hubert_model, version
    if input_audio_path is None:
        return "Você precisa enviar um áudio.", None
    f0_up_key = int(f0_up_key)
    try:
        audio = load_audio(input_audio_path, 16000)
        audio_max = np.abs(audio).max() / 0.95
        if audio_max > 1:
            audio /= audio_max
        times = [0, 0, 0]
        if hubert_model == None:
            load_hubert()
        if_f0 = cpt.get("f0", 1)
        file_index = (
            (
                file_index.strip(" ")
                .strip('"')
                .strip("\n")
                .strip('"')
                .strip(" ")
                .replace("treinado", "adicionado")
            )
        )  # 防止小白写错，自动帮他替换掉
        # file_big_npy = (
        #     file_big_npy.strip(" ").strip('"').strip("\n").strip('"').strip(" ")
        # )
        audio_opt = vc.pipeline(
            hubert_model,
            net_g,
            sid,
            audio,
            input_audio_path,
            times,
            f0_up_key,
            f0_method,
            file_index,
            # file_big_npy,
            index_rate,
            if_f0,
            filter_radius,
            tgt_sr,
            resample_sr,
            rms_mix_rate,
            version,
            protect,
            crepe_hop_length,
            f0_file=f0_file,
        )
        if resample_sr >= 16000 and tgt_sr != resample_sr:
            tgt_sr = resample_sr
        index_info = (
            "Utilizando index:%s." % file_index
            if os.path.exists(file_index)
            else "Index não utilizado."
        )
        return "Succeso.\n %s\nTime:\n npy:%ss, f0:%ss, infer:%ss" % (
            index_info,
            times[0],
            times[1],
            times[2],
        ), (tgt_sr, audio_opt)
    except:
        info = traceback.format_exc()
        print(info)
        return info, (None, None)


def vc_multi(
    sid,
    dir_path,
    opt_root,
    paths,
    f0_up_key,
    f0_method,
    file_index,
    file_index2,
    # file_big_npy,
    index_rate,
    filter_radius,
    resample_sr,
    rms_mix_rate,
    protect,
    format1,
    crepe_hop_length,
):
    try:
        dir_path = (
            dir_path.strip(" ").strip('"').strip("\n").strip('"').strip(" ")
        )  # 防止小白拷路径头尾带了空格和"和回车
        opt_root = opt_root.strip(" ").strip('"').strip("\n").strip('"').strip(" ")
        os.makedirs(opt_root, exist_ok=True)
        try:
            if dir_path != "":
                paths = [os.path.join(dir_path, name) for name in os.listdir(dir_path)]
            else:
                paths = [path.name for path in paths]
        except:
            traceback.print_exc()
            paths = [path.name for path in paths]
        infos = []
        for path in paths:
            info, opt = vc_single(
                sid,
                path,
                f0_up_key,
                None,
                f0_method,
                file_index,
                file_index2,
                # file_big_npy,
                index_rate,
                filter_radius,
                resample_sr,
                rms_mix_rate,
                protect,
                crepe_hop_length
            )
            if "Success" in info:
                try:
                    tgt_sr, audio_opt = opt
                    if format1 in ["wav", "flac"]:
                        sf.write(
                            "%s/%s.%s" % (opt_root, os.path.basename(path), format1),
                            audio_opt,
                            tgt_sr,
                        )
                    else:
                        path = "%s/%s.wav" % (opt_root, os.path.basename(path))
                        sf.write(
                            path,
                            audio_opt,
                            tgt_sr,
                        )
                        if os.path.exists(path):
                            os.system(
                                "ffmpeg -i %s -vn %s -q:a 2 -y"
                                % (path, path[:-4] + ".%s" % format1)
                            )
                except:
                    info += traceback.format_exc()
            infos.append("%s->%s" % (os.path.basename(path), info))
            yield "\n".join(infos)
        yield "\n".join(infos)
    except:
        yield traceback.format_exc()


def uvr(model_name, inp_root, save_root_vocal, paths, save_root_ins, agg, format0):
    infos = []
    try:
        inp_root = inp_root.strip(" ").strip('"').strip("\n").strip('"').strip(" ")
        save_root_vocal = (
            save_root_vocal.strip(" ").strip('"').strip("\n").strip('"').strip(" ")
        )
        save_root_ins = (
            save_root_ins.strip(" ").strip('"').strip("\n").strip('"').strip(" ")
        )
        if model_name == "onnx_dereverb_By_FoxJoy":
            pre_fun = MDXNetDereverb(15)
        else:
            func = _audio_pre_ if "DeEcho" not in model_name else _audio_pre_new
            pre_fun = func(
                agg=int(agg),
                model_path=os.path.join(weight_uvr5_root, model_name + ".pth"),
                device=config.device,
                is_half=config.is_half,
            )
        if inp_root != "":
            paths = [os.path.join(inp_root, name) for name in os.listdir(inp_root)]
        else:
            paths = [path.name for path in paths]
        for path in paths:
            inp_path = os.path.join(inp_root, path)
            need_reformat = 1
            done = 0
            try:
                info = ffmpeg.probe(inp_path, cmd="ffprobe")
                if (
                    info["streams"][0]["channels"] == 2
                    and info["streams"][0]["sample_rate"] == "44100"
                ):
                    need_reformat = 0
                    pre_fun._path_audio_(
                        inp_path, save_root_ins, save_root_vocal, format0
                    )
                    done = 1
            except:
                need_reformat = 1
                traceback.print_exc()
            if need_reformat == 1:
                tmp_path = "%s/%s.reformatted.wav" % (tmp, os.path.basename(inp_path))
                os.system(
                    "ffmpeg -i %s -vn -acodec pcm_s16le -ac 2 -ar 44100 %s -y"
                    % (inp_path, tmp_path)
                )
                inp_path = tmp_path
            try:
                if done == 0:
                    pre_fun._path_audio_(
                        inp_path, save_root_ins, save_root_vocal, format0
                    )
                infos.append("%s->Success" % (os.path.basename(inp_path)))
                yield "\n".join(infos)
            except:
                infos.append(
                    "%s->%s" % (os.path.basename(inp_path), traceback.format_exc())
                )
                yield "\n".join(infos)
    except:
        infos.append(traceback.format_exc())
        yield "\n".join(infos)
    finally:
        try:
            if model_name == "onnx_dereverb_By_FoxJoy":
                del pre_fun.pred.model
                del pre_fun.pred.model_
            else:
                del pre_fun.model
                del pre_fun
        except:
            traceback.print_exc()
        print("clean_empty_cache")
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    yield "\n".join(infos)


# 一个选项卡全局只能有一个音色
def get_vc(sid):
    global n_spk, tgt_sr, net_g, vc, cpt, version
    if sid == "" or sid == []:
        global hubert_model
        if hubert_model != None:  # 考虑到轮询, 需要加个判断看是否 sid 是由有模型切换到无模型的
            print("clean_empty_cache")
            del net_g, n_spk, vc, hubert_model, tgt_sr  # ,cpt
            hubert_model = net_g = n_spk = vc = hubert_model = tgt_sr = None
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            ###楼下不这么折腾清理不干净
            if_f0 = cpt.get("f0", 1)
            version = cpt.get("version", "v1")
            if version == "v1":
                if if_f0 == 1:
                    net_g = SynthesizerTrnMs256NSFsid(
                        *cpt["config"], is_half=config.is_half
                    )
                else:
                    net_g = SynthesizerTrnMs256NSFsid_nono(*cpt["config"])
            elif version == "v2":
                if if_f0 == 1:
                    net_g = SynthesizerTrnMs768NSFsid(
                        *cpt["config"], is_half=config.is_half
                    )
                else:
                    net_g = SynthesizerTrnMs768NSFsid_nono(*cpt["config"])
            del net_g, cpt
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            cpt = None
        return {"visible": False, "__type__": "update"}
    person = "%s/%s" % (weight_root, sid)
    print("loading %s" % person)
    cpt = torch.load(person, map_location="cpu")
    tgt_sr = cpt["config"][-1]
    cpt["config"][-3] = cpt["weight"]["emb_g.weight"].shape[0]  # n_spk
    if_f0 = cpt.get("f0", 1)
    version = cpt.get("version", "v1")
    if version == "v1":
        if if_f0 == 1:
            net_g = SynthesizerTrnMs256NSFsid(*cpt["config"], is_half=config.is_half)
        else:
            net_g = SynthesizerTrnMs256NSFsid_nono(*cpt["config"])
    elif version == "v2":
        if if_f0 == 1:
            net_g = SynthesizerTrnMs768NSFsid(*cpt["config"], is_half=config.is_half)
        else:
            net_g = SynthesizerTrnMs768NSFsid_nono(*cpt["config"])
    del net_g.enc_q
    print(net_g.load_state_dict(cpt["weight"], strict=False))
    net_g.eval().to(config.device)
    if config.is_half:
        net_g = net_g.half()
    else:
        net_g = net_g.float()
    vc = VC(tgt_sr, config)
    n_spk = cpt["config"][-3]
    return {"visible": False, "maximum": n_spk, "__type__": "update"}


def change_choices():
    names = []
    for name in os.listdir(weight_root):
        if name.endswith(".pth"):
            names.append(name)
    index_paths = []
    for root, dirs, files in os.walk(index_root, topdown=False):
        for name in files:
            if name.endswith(".index") and "treinado" not in name:
                index_paths.append("%s/%s" % (root, name))
    return {"choices": sorted(names), "__type__": "update"}, {
        "choices": sorted(index_paths),
        "__type__": "update",
    }


def clean():
    return {"valor": "", "__type__": "update"}


sr_dict = {
    "32k": 32000,
    "40k": 40000,
    "48k": 48000,
}


def if_done(done, p):
    while 1:
        if p.poll() == None:
            sleep(0.5)
        else:
            break
    done[0] = True


def if_done_multi(done, ps):
    while 1:
        # poll==None代表进程未结束
        # 只要有一个进程未结束都不停
        flag = 1
        for p in ps:
            if p.poll() == None:
                flag = 0
                sleep(0.5)
                break
        if flag == 1:
            break
    done[0] = True


def preprocess_dataset(trainset_dir, exp_dir, sr, n_p):
    sr = sr_dict[sr]
    os.makedirs("%s/logs/%s" % (now_dir, exp_dir), exist_ok=True)
    f = open("%s/logs/%s/preprocess.log" % (now_dir, exp_dir), "w")
    f.close()
    cmd = (
        config.python_cmd
        + " trainset_preprocess_pipeline_print.py %s %s %s %s/logs/%s "
        % (trainset_dir, sr, n_p, now_dir, exp_dir)
        + str(config.noparallel)
    )
    print(cmd)
    p = Popen(cmd, shell=True)  # , stdin=PIPE, stdout=PIPE,stderr=PIPE,cwd=now_dir
    ###煞笔gr, popen read都非得全跑完了再一次性读取, 不用gr就正常读一句输出一句;只能额外弄出一个文本流定时读
    done = [False]
    threading.Thread(
        target=if_done,
        args=(
            done,
            p,
        ),
    ).start()
    while 1:
        with open("%s/logs/%s/preprocess.log" % (now_dir, exp_dir), "r") as f:
            yield (f.read())
        sleep(1)
        if done[0] == True:
            break
    with open("%s/logs/%s/preprocess.log" % (now_dir, exp_dir), "r") as f:
        log = f.read()
    print(log)
    yield log


# but2.click(extract_f0,[gpus6,np7,f0method8,if_f0_3,trainset_dir4],[info2])
def extract_f0_feature(gpus, n_p, f0method, if_f0, exp_dir, version19, echl):
    gpus = gpus.split("-")
    os.makedirs("%s/logs/%s" % (now_dir, exp_dir), exist_ok=True)
    f = open("%s/logs/%s/extract_f0_feature.log" % (now_dir, exp_dir), "w")
    f.close()
    if if_f0:
        cmd = config.python_cmd + " extract_f0_print.py %s/logs/%s %s %s %s" % (
            now_dir,
            exp_dir,
            n_p,
            f0method,
            echl,
        )
        print(cmd)
        p = Popen(cmd, shell=True, cwd=now_dir)  # , stdin=PIPE, stdout=PIPE,stderr=PIPE
        ###煞笔gr, popen read都非得全跑完了再一次性读取, 不用gr就正常读一句输出一句;只能额外弄出一个文本流定时读
        done = [False]
        threading.Thread(
            target=if_done,
            args=(
                done,
                p,
            ),
        ).start()
        while 1:
            with open(
                "%s/logs/%s/extract_f0_feature.log" % (now_dir, exp_dir), "r"
            ) as f:
                yield (f.read())
            sleep(1)
            if done[0] == True:
                break
        with open("%s/logs/%s/extract_f0_feature.log" % (now_dir, exp_dir), "r") as f:
            log = f.read()
        print(log)
        yield log
    ####对不同part分别开多进程
    """
    n_part=int(sys.argv[1])
    i_part=int(sys.argv[2])
    i_gpu=sys.argv[3]
    exp_dir=sys.argv[4]
    os.environ["CUDA_VISIBLE_DEVICES"]=str(i_gpu)
    """
    leng = len(gpus)
    ps = []
    for idx, n_g in enumerate(gpus):
        cmd = (
            config.python_cmd
            + " extract_feature_print.py %s %s %s %s %s/logs/%s %s"
            % (
                config.device,
                leng,
                idx,
                n_g,
                now_dir,
                exp_dir,
                version19,
            )
        )
        print(cmd)
        p = Popen(
            cmd, shell=True, cwd=now_dir
        )  # , shell=True, stdin=PIPE, stdout=PIPE, stderr=PIPE, cwd=now_dir
        ps.append(p)
    ###煞笔gr, popen read都非得全跑完了再一次性读取, 不用gr就正常读一句输出一句;只能额外弄出一个文本流定时读
    done = [False]
    threading.Thread(
        target=if_done_multi,
        args=(
            done,
            ps,
        ),
    ).start()
    while 1:
        with open("%s/logs/%s/extract_f0_feature.log" % (now_dir, exp_dir), "r") as f:
            yield (f.read())
        sleep(1)
        if done[0] == True:
            break
    with open("%s/logs/%s/extract_f0_feature.log" % (now_dir, exp_dir), "r") as f:
        log = f.read()
    print(log)
    yield log


def change_sr2(sr2, if_f0_3, version19):
    path_str = "" if version19 == "v1" else "_v2"
    f0_str = "f0" if if_f0_3 else ""
    if_pretrained_generator_exist = os.access("pretrained%s/%sG%s.pth" % (path_str, f0_str, sr2), os.F_OK)
    if_pretrained_discriminator_exist = os.access("pretrained%s/%sD%s.pth" % (path_str, f0_str, sr2), os.F_OK)
    if (if_pretrained_generator_exist == False):
        print("pretrained%s/%sG%s.pth" % (path_str, f0_str, sr2), "not exist, will not use pretrained model")
    if (if_pretrained_discriminator_exist == False):
        print("pretrained%s/%sD%s.pth" % (path_str, f0_str, sr2), "not exist, will not use pretrained model")
    return (
        ("pretrained%s/%sG%s.pth" % (path_str, f0_str, sr2)) if if_pretrained_generator_exist else "",
        ("pretrained%s/%sD%s.pth" % (path_str, f0_str, sr2)) if if_pretrained_discriminator_exist else "",
        {"visible": True, "__type__": "update"}
    )

def change_version19(sr2, if_f0_3, version19):
    path_str = "" if version19 == "v1" else "_v2"
    f0_str = "f0" if if_f0_3 else ""
    if_pretrained_generator_exist = os.access("pretrained%s/%sG%s.pth" % (path_str, f0_str, sr2), os.F_OK)
    if_pretrained_discriminator_exist = os.access("pretrained%s/%sD%s.pth" % (path_str, f0_str, sr2), os.F_OK)
    if (if_pretrained_generator_exist == False):
        print("pretrained%s/%sG%s.pth" % (path_str, f0_str, sr2), "não existe, não será utilizado modelo pre-treinado.")
    if (if_pretrained_discriminator_exist == False):
        print("pretrained%s/%sD%s.pth" % (path_str, f0_str, sr2), "não existe, não será utilizado modelo pre-treinado.")
    return (
        ("pretrained%s/%sG%s.pth" % (path_str, f0_str, sr2)) if if_pretrained_generator_exist else "",
        ("pretrained%s/%sD%s.pth" % (path_str, f0_str, sr2)) if if_pretrained_discriminator_exist else "",
    )


def change_f0(if_f0_3, sr2, version19):  # f0method8,pretrained_G14,pretrained_D15
    path_str = "" if version19 == "v1" else "_v2"
    if_pretrained_generator_exist = os.access("pretrained%s/f0G%s.pth" % (path_str, sr2), os.F_OK)
    if_pretrained_discriminator_exist = os.access("pretrained%s/f0D%s.pth" % (path_str, sr2), os.F_OK)
    if (if_pretrained_generator_exist == False):
        print("pretrained%s/f0G%s.pth" % (path_str, sr2), "não existe, não será utilizado modelo pre-treinado.")
    if (if_pretrained_discriminator_exist == False):
        print("pretrained%s/f0D%s.pth" % (path_str, sr2), "não existe, não será utilizado modelo pre-treinado.")
    if if_f0_3:
        return (
            {"visible": True, "__type__": "update"},
            "pretrained%s/f0G%s.pth" % (path_str, sr2) if if_pretrained_generator_exist else "",
            "pretrained%s/f0D%s.pth" % (path_str, sr2) if if_pretrained_discriminator_exist else "",
        )
    return (
        {"visible": False, "__type__": "update"},
        ("pretrained%s/G%s.pth" % (path_str, sr2)) if if_pretrained_generator_exist else "",
        ("pretrained%s/D%s.pth" % (path_str, sr2)) if if_pretrained_discriminator_exist else "",
    )


# but3.click(click_train,[exp_dir1,sr2,if_f0_3,save_epoch10,total_epoch11,batch_size12,if_save_latest13,pretrained_G14,pretrained_D15,gpus16])
def click_train(
    exp_dir1,
    sr2,
    if_f0_3,
    spk_id5,
    save_epoch10,
    total_epoch11,
    batch_size12,
    if_save_latest13,
    pretrained_G14,
    pretrained_D15,
    gpus16,
    if_cache_gpu17,
    if_save_every_weights18,
    version19,
):
    # 生成filelist
    exp_dir = "%s/logs/%s" % (now_dir, exp_dir1)
    os.makedirs(exp_dir, exist_ok=True)
    gt_wavs_dir = "%s/0_gt_wavs" % (exp_dir)
    feature_dir = (
        "%s/3_feature256" % (exp_dir)
        if version19 == "v1"
        else "%s/3_feature768" % (exp_dir)
    )
    if if_f0_3:
        f0_dir = "%s/2a_f0" % (exp_dir)
        f0nsf_dir = "%s/2b-f0nsf" % (exp_dir)
        names = (
            set([name.split(".")[0] for name in os.listdir(gt_wavs_dir)])
            & set([name.split(".")[0] for name in os.listdir(feature_dir)])
            & set([name.split(".")[0] for name in os.listdir(f0_dir)])
            & set([name.split(".")[0] for name in os.listdir(f0nsf_dir)])
        )
    else:
        names = set([name.split(".")[0] for name in os.listdir(gt_wavs_dir)]) & set(
            [name.split(".")[0] for name in os.listdir(feature_dir)]
        )
    opt = []
    for name in names:
        if if_f0_3:
            opt.append(
                "%s/%s.wav|%s/%s.npy|%s/%s.wav.npy|%s/%s.wav.npy|%s"
                % (
                    gt_wavs_dir.replace("\\", "\\\\"),
                    name,
                    feature_dir.replace("\\", "\\\\"),
                    name,
                    f0_dir.replace("\\", "\\\\"),
                    name,
                    f0nsf_dir.replace("\\", "\\\\"),
                    name,
                    spk_id5,
                )
            )
        else:
            opt.append(
                "%s/%s.wav|%s/%s.npy|%s"
                % (
                    gt_wavs_dir.replace("\\", "\\\\"),
                    name,
                    feature_dir.replace("\\", "\\\\"),
                    name,
                    spk_id5,
                )
            )
    fea_dim = 256 if version19 == "v1" else 768
    if if_f0_3:
        for _ in range(2):
            opt.append(
                "%s/logs/mute/0_gt_wavs/mute%s.wav|%s/logs/mute/3_feature%s/mute.npy|%s/logs/mute/2a_f0/mute.wav.npy|%s/logs/mute/2b-f0nsf/mute.wav.npy|%s"
                % (now_dir, sr2, now_dir, fea_dim, now_dir, now_dir, spk_id5)
            )
    else:
        for _ in range(2):
            opt.append(
                "%s/logs/mute/0_gt_wavs/mute%s.wav|%s/logs/mute/3_feature%s/mute.npy|%s"
                % (now_dir, sr2, now_dir, fea_dim, spk_id5)
            )
    shuffle(opt)
    with open("%s/filelist.txt" % exp_dir, "w") as f:
        f.write("\n".join(opt))
    print("write filelist done")
    # 生成config#无需生成config
    # cmd = python_cmd + " train_nsf_sim_cache_sid_load_pretrain.py -e mi-test -sr 40k -f0 1 -bs 4 -g 0 -te 10 -se 5 -pg pretrained/f0G40k.pth -pd pretrained/f0D40k.pth -l 1 -c 0"
    print("use gpus:", gpus16)
    if pretrained_G14 == "":
        print("no pretrained Generator")
    if pretrained_D15 == "":
        print("no pretrained Discriminator")
    if gpus16:
        cmd = (
            config.python_cmd
            + " train_nsf_sim_cache_sid_load_pretrain.py -e %s -sr %s -f0 %s -bs %s -g %s -te %s -se %s %s %s -l %s -c %s -sw %s -v %s"
            % (
                exp_dir1,
                sr2,
                1 if if_f0_3 else 0,
                batch_size12,
                gpus16,
                total_epoch11,
                save_epoch10,
                ("-pg %s" % pretrained_G14) if pretrained_G14 != "" else "",
                ("-pd %s" % pretrained_D15) if pretrained_D15 != "" else "",
                1 if if_save_latest13 == i18n("是") else 0,
                1 if if_cache_gpu17 == i18n("是") else 0,
                1 if if_save_every_weights18 == i18n("是") else 0,
                version19,
            )
        )
    else:
        cmd = (
            config.python_cmd
            + " train_nsf_sim_cache_sid_load_pretrain.py -e %s -sr %s -f0 %s -bs %s -te %s -se %s %s %s -l %s -c %s -sw %s -v %s"
            % (
                exp_dir1,
                sr2,
                1 if if_f0_3 else 0,
                batch_size12,
                total_epoch11,
                save_epoch10,
                ("-pg %s" % pretrained_G14) if pretrained_G14 != "" else "\b",
                ("-pd %s" % pretrained_D15) if pretrained_D15 != "" else "\b",
                1 if if_save_latest13 == i18n("是") else 0,
                1 if if_cache_gpu17 == i18n("是") else 0,
                1 if if_save_every_weights18 == i18n("是") else 0,
                version19,
            )
        )
    print(cmd)
    p = Popen(cmd, shell=True, cwd=now_dir)
    p.wait()
    return "Após terminar o treinamento, o log será salvo em train.log, na pasta log"


# but4.click(train_index, [exp_dir1], info3)
def train_index(exp_dir1, version19):
    exp_dir = "%s/logs/%s" % (now_dir, exp_dir1)
    os.makedirs(exp_dir, exist_ok=True)
    feature_dir = (
        "%s/3_feature256" % (exp_dir)
        if version19 == "v1"
        else "%s/3_feature768" % (exp_dir)
    )
    if os.path.exists(feature_dir) == False:
        return "Execute a extração de pitch primeiro!"
    listdir_res = list(os.listdir(feature_dir))
    if len(listdir_res) == 0:
        return "Execute a extração de pitch primeiro!"
    npys = []
    for name in sorted(listdir_res):
        phone = np.load("%s/%s" % (feature_dir, name))
        npys.append(phone)
    big_npy = np.concatenate(npys, 0)
    big_npy_idx = np.arange(big_npy.shape[0])
    np.random.shuffle(big_npy_idx)
    big_npy = big_npy[big_npy_idx]
    np.save("%s/total_fea.npy" % exp_dir, big_npy)
    # n_ivf =  big_npy.shape[0] // 39
    n_ivf = min(int(16 * np.sqrt(big_npy.shape[0])), big_npy.shape[0] // 39)
    infos = []
    infos.append("%s,%s" % (big_npy.shape, n_ivf))
    yield "\n".join(infos)
    index = faiss.index_factory(256 if version19 == "v1" else 768, "IVF%s,Flat" % n_ivf)
    # index = faiss.index_factory(256if version19=="v1"else 768, "IVF%s,PQ128x4fs,RFlat"%n_ivf)
    infos.append("training")
    yield "\n".join(infos)
    index_ivf = faiss.extract_index_ivf(index)  #
    index_ivf.nprobe = 1
    index.train(big_npy)
    faiss.write_index(
        index,
        "%s/trained_IVF%s_Flat_nprobe_%s_%s_%s.index"
        % (exp_dir, n_ivf, index_ivf.nprobe, exp_dir1, version19),
    )
    # faiss.write_index(index, '%s/trained_IVF%s_Flat_FastScan_%s.index'%(exp_dir,n_ivf,version19))
    infos.append("adding")
    yield "\n".join(infos)
    batch_size_add = 8192
    for i in range(0, big_npy.shape[0], batch_size_add):
        index.add(big_npy[i : i + batch_size_add])
    faiss.write_index(
        index,
        "%s/added_IVF%s_Flat_nprobe_%s_%s_%s.index"
        % (exp_dir, n_ivf, index_ivf.nprobe, exp_dir1, version19),
    )
    infos.append(
        "Index criado, com nome de: added_IVF%s_Flat_nprobe_%s_%s_%s.index"
        % (n_ivf, index_ivf.nprobe, exp_dir1, version19)
    )
    # faiss.write_index(index, '%s/added_IVF%s_Flat_FastScan_%s.index'%(exp_dir,n_ivf,version19))
    # infos.append("成功构建索引，added_IVF%s_Flat_FastScan_%s.index"%(n_ivf,version19))
    yield "\n".join(infos)


# but5.click(train1key, [exp_dir1, sr2, if_f0_3, trainset_dir4, spk_id5, gpus6, np7, f0method8, save_epoch10, total_epoch11, batch_size12, if_save_latest13, pretrained_G14, pretrained_D15, gpus16, if_cache_gpu17], info3)
def train1key(
    exp_dir1,
    sr2,
    if_f0_3,
    trainset_dir4,
    spk_id5,
    np7,
    f0method8,
    save_epoch10,
    total_epoch11,
    batch_size12,
    if_save_latest13,
    pretrained_G14,
    pretrained_D15,
    gpus16,
    if_cache_gpu17,
    if_save_every_weights18,
    version19,
    echl
):
    infos = []

    def get_info_str(strr):
        infos.append(strr)
        return "\n".join(infos)

    model_log_dir = "%s/logs/%s" % (now_dir, exp_dir1)
    preprocess_log_path = "%s/preprocess.log" % model_log_dir
    extract_f0_feature_log_path = "%s/extract_f0_feature.log" % model_log_dir
    gt_wavs_dir = "%s/0_gt_wavs" % model_log_dir
    feature_dir = (
        "%s/3_feature256" % model_log_dir
        if version19 == "v1"
        else "%s/3_feature768" % model_log_dir
    )

    os.makedirs(model_log_dir, exist_ok=True)
    #########step1:处理数据
    open(preprocess_log_path, "w").close()
    cmd = (
        config.python_cmd
        + " trainset_preprocess_pipeline_print.py %s %s %s %s "
        % (trainset_dir4, sr_dict[sr2], np7, model_log_dir)
        + str(config.noparallel)
    )
    yield get_info_str(i18n("Passo 1: Processando dados"))
    yield get_info_str(cmd)
    p = Popen(cmd, shell=True)
    p.wait()
    with open(preprocess_log_path, "r") as f:
        print(f.read())
    #########step2a:提取音高
    open(extract_f0_feature_log_path, "w")
    if if_f0_3:
        yield get_info_str("Passo 2: extraindo pitch")
        cmd = config.python_cmd + " extract_f0_print.py %s %s %s %s" % (
            model_log_dir,
            np7,
            f0method8,
            echl
        )
        yield get_info_str(cmd)
        p = Popen(cmd, shell=True, cwd=now_dir)
        p.wait()
        with open(extract_f0_feature_log_path, "r") as f:
            print(f.read())
    else:
        yield get_info_str(i18n("Passo 2a: Não precisa extrair pitch, provavelmente já foi feito."))
    #######step2b:提取特征
    yield get_info_str(i18n("Passo 2b: Extraindo pitch."))
    gpus = gpus16.split("-")
    leng = len(gpus)
    ps = []
    for idx, n_g in enumerate(gpus):
        cmd = config.python_cmd + " extract_feature_print.py %s %s %s %s %s %s" % (
            config.device,
            leng,
            idx,
            n_g,
            model_log_dir,
            version19,
        )
        yield get_info_str(cmd)
        p = Popen(
            cmd, shell=True, cwd=now_dir
        )  # , shell=True, stdin=PIPE, stdout=PIPE, stderr=PIPE, cwd=now_dir
        ps.append(p)
    for p in ps:
        p.wait()
    with open(extract_f0_feature_log_path, "r") as f:
        print(f.read())
    #######step3a:训练模型
    yield get_info_str(i18n("Passo 3a: Modelo de treinamento"))
    # 生成filelist
    if if_f0_3:
        f0_dir = "%s/2a_f0" % model_log_dir
        f0nsf_dir = "%s/2b-f0nsf" % model_log_dir
        names = (
            set([name.split(".")[0] for name in os.listdir(gt_wavs_dir)])
            & set([name.split(".")[0] for name in os.listdir(feature_dir)])
            & set([name.split(".")[0] for name in os.listdir(f0_dir)])
            & set([name.split(".")[0] for name in os.listdir(f0nsf_dir)])
        )
    else:
        names = set([name.split(".")[0] for name in os.listdir(gt_wavs_dir)]) & set(
            [name.split(".")[0] for name in os.listdir(feature_dir)]
        )
    opt = []
    for name in names:
        if if_f0_3:
            opt.append(
                "%s/%s.wav|%s/%s.npy|%s/%s.wav.npy|%s/%s.wav.npy|%s"
                % (
                    gt_wavs_dir.replace("\\", "\\\\"),
                    name,
                    feature_dir.replace("\\", "\\\\"),
                    name,
                    f0_dir.replace("\\", "\\\\"),
                    name,
                    f0nsf_dir.replace("\\", "\\\\"),
                    name,
                    spk_id5,
                )
            )
        else:
            opt.append(
                "%s/%s.wav|%s/%s.npy|%s"
                % (
                    gt_wavs_dir.replace("\\", "\\\\"),
                    name,
                    feature_dir.replace("\\", "\\\\"),
                    name,
                    spk_id5,
                )
            )
    fea_dim = 256 if version19 == "v1" else 768
    if if_f0_3:
        for _ in range(2):
            opt.append(
                "%s/logs/mute/0_gt_wavs/mute%s.wav|%s/logs/mute/3_feature%s/mute.npy|%s/logs/mute/2a_f0/mute.wav.npy|%s/logs/mute/2b-f0nsf/mute.wav.npy|%s"
                % (now_dir, sr2, now_dir, fea_dim, now_dir, now_dir, spk_id5)
            )
    else:
        for _ in range(2):
            opt.append(
                "%s/logs/mute/0_gt_wavs/mute%s.wav|%s/logs/mute/3_feature%s/mute.npy|%s"
                % (now_dir, sr2, now_dir, fea_dim, spk_id5)
            )
    shuffle(opt)
    with open("%s/filelist.txt" % model_log_dir, "w") as f:
        f.write("\n".join(opt))
    yield get_info_str("write filelist done")
    if gpus16:
        cmd = (
            config.python_cmd
            +" train_nsf_sim_cache_sid_load_pretrain.py -e %s -sr %s -f0 %s -bs %s -g %s -te %s -se %s %s %s -l %s -c %s -sw %s -v %s"
            % (
                exp_dir1,
                sr2,
                1 if if_f0_3 else 0,
                batch_size12,
                gpus16,
                total_epoch11,
                save_epoch10,
                ("-pg %s" % pretrained_G14) if pretrained_G14 != "" else "",
                ("-pd %s" % pretrained_D15) if pretrained_D15 != "" else "",
                1 if if_save_latest13 == i18n("是") else 0,
                1 if if_cache_gpu17 == i18n("是") else 0,
                1 if if_save_every_weights18 == i18n("是") else 0,
                version19,
            )
        )
    else:
        cmd = (
            config.python_cmd
            + " train_nsf_sim_cache_sid_load_pretrain.py -e %s -sr %s -f0 %s -bs %s -te %s -se %s %s %s -l %s -c %s -sw %s -v %s"
            % (
                exp_dir1,
                sr2,
                1 if if_f0_3 else 0,
                batch_size12,
                total_epoch11,
                save_epoch10,
                ("-pg %s" % pretrained_G14) if pretrained_G14 != "" else "",
                ("-pd %s" % pretrained_D15) if pretrained_D15 != "" else "",
                1 if if_save_latest13 == i18n("是") else 0,
                1 if if_cache_gpu17 == i18n("是") else 0,
                1 if if_save_every_weights18 == i18n("是") else 0,
                version19,
            )
        )
    yield get_info_str(cmd)
    p = Popen(cmd, shell=True, cwd=now_dir)
    p.wait()
    yield get_info_str(i18n("Após treino concluído, log será salvo na pasta logs com nome de train.log"))
    #######step3b:训练索引
    npys = []
    listdir_res = list(os.listdir(feature_dir))
    for name in sorted(listdir_res):
        phone = np.load("%s/%s" % (feature_dir, name))
        npys.append(phone)
    big_npy = np.concatenate(npys, 0)

    big_npy_idx = np.arange(big_npy.shape[0])
    np.random.shuffle(big_npy_idx)
    big_npy = big_npy[big_npy_idx]
    np.save("%s/total_fea.npy" % model_log_dir, big_npy)

    # n_ivf =  big_npy.shape[0] // 39
    n_ivf = min(int(16 * np.sqrt(big_npy.shape[0])), big_npy.shape[0] // 39)
    yield get_info_str("%s,%s" % (big_npy.shape, n_ivf))
    index = faiss.index_factory(256 if version19 == "v1" else 768, "IVF%s,Flat" % n_ivf)
    yield get_info_str("training index")
    index_ivf = faiss.extract_index_ivf(index)  #
    index_ivf.nprobe = 1
    index.train(big_npy)
    faiss.write_index(
        index,
        "%s/trained_IVF%s_Flat_nprobe_%s_%s_%s.index"
        % (model_log_dir, n_ivf, index_ivf.nprobe, exp_dir1, version19),
    )
    yield get_info_str("adicionando index")
    batch_size_add = 8192
    for i in range(0, big_npy.shape[0], batch_size_add):
        index.add(big_npy[i : i + batch_size_add])
    faiss.write_index(
        index,
        "%s/added_IVF%s_Flat_nprobe_%s_%s_%s.index"
        % (model_log_dir, n_ivf, index_ivf.nprobe, exp_dir1, version19),
    )
    yield get_info_str(
        "Index criado com sucesso, com nome de: added_IVF%s_Flat_nprobe_%s_%s_%s.index"
        % (n_ivf, index_ivf.nprobe, exp_dir1, version19)
    )
    yield get_info_str(i18n("Processo finalizado！"))


#                    ckpt_path2.change(change_info_,[ckpt_path2],[sr__,if_f0__])
def change_info_(ckpt_path):
    if (
        os.path.exists(ckpt_path.replace(os.path.basename(ckpt_path), "train.log"))
        == False
    ):
        return {"__type__": "update"}, {"__type__": "update"}, {"__type__": "update"}
    try:
        with open(
            ckpt_path.replace(os.path.basename(ckpt_path), "train.log"), "r"
        ) as f:
            info = eval(f.read().strip("\n").split("\n")[0].split("\t")[-1])
            sr, f0 = info["sample_rate"], info["if_f0"]
            version = "v2" if ("version" in info and info["version"] == "v2") else "v1"
            return sr, str(f0), version
    except:
        traceback.print_exc()
        return {"__type__": "update"}, {"__type__": "update"}, {"__type__": "update"}


from infer_pack.models_onnx import SynthesizerTrnMsNSFsidM


def export_onnx(ModelPath, ExportedPath, MoeVS=True):
    cpt = torch.load(ModelPath, map_location="cpu")
    cpt["config"][-3] = cpt["weight"]["emb_g.weight"].shape[0]  # n_spk
    hidden_channels = 256 if cpt.get("version","v1")=="v1"else 768#cpt["config"][-2]  # hidden_channels，为768Vec做准备

    test_phone = torch.rand(1, 200, hidden_channels)  # hidden unit
    test_phone_lengths = torch.tensor([200]).long()  # hidden unit 长度（貌似没啥用）
    test_pitch = torch.randint(size=(1, 200), low=5, high=255)  # 基频（单位赫兹）
    test_pitchf = torch.rand(1, 200)  # nsf基频
    test_ds = torch.LongTensor([0])  # 说话人ID
    test_rnd = torch.rand(1, 192, 200)  # 噪声（加入随机因子）

    device = "cpu"  # 导出时设备（不影响使用模型）


    net_g = SynthesizerTrnMsNSFsidM(
        *cpt["config"], is_half=False,version=cpt.get("version","v1")
    )  # fp32导出（C++要支持fp16必须手动将内存重新排列所以暂时不用fp16）
    net_g.load_state_dict(cpt["weight"], strict=False)
    input_names = ["phone", "phone_lengths", "pitch", "pitchf", "ds", "rnd"]
    output_names = [
        "audio",
    ]
    # net_g.construct_spkmixmap(n_speaker) 多角色混合轨道导出
    torch.onnx.export(
        net_g,
        (
            test_phone.to(device),
            test_phone_lengths.to(device),
            test_pitch.to(device),
            test_pitchf.to(device),
            test_ds.to(device),
            test_rnd.to(device),
        ),
        ExportedPath,
        dynamic_axes={
            "phone": [1],
            "pitch": [1],
            "pitchf": [1],
            "rnd": [2],
        },
        do_constant_folding=False,
        opset_version=16,
        verbose=False,
        input_names=input_names,
        output_names=output_names,
    )
    return "Finished"


#region Mangio-RVC-Fork CLI App
import re as regex
import scipy.io.wavfile as wavfile

cli_current_page = "HOME"

def cli_split_command(com):
    exp = r'(?:(?<=\s)|^)"(.*?)"(?=\s|$)|(\S+)'
    split_array = regex.findall(exp, com)
    split_array = [group[0] if group[0] else group[1] for group in split_array]
    return split_array

def execute_generator_function(genObject):
    for _ in genObject: pass

def cli_infer(com):
    # get VC first
    com = cli_split_command(com)
    model_name = com[0]
    source_audio_path = com[1]
    output_file_name = com[2]
    feature_index_path = com[3]
    f0_file = None # Not Implemented Yet

    # Get parameters for inference
    speaker_id = int(com[4])
    transposition = float(com[5])
    f0_method = com[6]
    crepe_hop_length = int(com[7])
    harvest_median_filter = int(com[8])
    resample = int(com[9])
    mix = float(com[10])
    feature_ratio = float(com[11])
    protection_amnt = float(com[12])

    print("Mangio-RVC-Fork Infer-CLI: Iniciando a inferência...")
    vc_data = get_vc(model_name)
    print(vc_data)
    print("Mangio-RVC-Fork Infer-CLI: Realizando Inferência...")
    conversion_data = vc_single(
        speaker_id,
        source_audio_path,
        transposition,
        f0_file,
        f0_method,
        feature_index_path,
        #feature_index_path,
        feature_ratio,
        harvest_median_filter,
        resample,
        mix,
        protection_amnt,
        crepe_hop_length,        
    )
    if "Success." in conversion_data[0]:
        print("Mangio-RVC-Fork Infer-CLI: Concluida,Inference succeeded. Writing to %s/%s..." % ('audio-outputs', output_file_name))
        wavfile.write('%s/%s' % ('audio-outputs', output_file_name), conversion_data[1][0], conversion_data[1][1])
        print("Mangio-RVC-Fork Infer-CLI: Concluido, Salvo em  %s/%s" % ('audio-outputs', output_file_name))
    else:
        print("Mangio-RVC-Fork Infer-CLI: Inferência falhou. Segue o rastreio do erro:")
        print(conversion_data[0])

def cli_pre_process(com):
    com = cli_split_command(com)
    model_name = com[0]
    trainset_directory = com[1]
    sample_rate = com[2]
    num_processes = int(com[3])

    print("Mangio-RVC-Fork Pre-process: Iniciando...")
    generator = preprocess_dataset(
        trainset_directory, 
        model_name, 
        sample_rate, 
        num_processes
    )
    execute_generator_function(generator)
    print("Mangio-RVC-Fork Pre-process: Finalizado...")

def cli_extract_feature(com):
    com = cli_split_command(com)
    model_name = com[0]
    gpus = com[1]
    num_processes = int(com[2])
    has_pitch_guidance = True if (int(com[3]) == 1) else False
    f0_method = com[4]
    crepe_hop_length = int(com[5])
    version = com[6] # v1 or v2
    
    print("Mangio-RVC-CLI: Recurso de Extração de pitch tem: " + str(has_pitch_guidance))
    print("Mangio-RVC-CLI: Extrair versão: " + str(version))
    print("Mangio-RVC-Fork Extração de funcionalidades: Iniciando...")
    generator = extract_f0_feature(
        gpus, 
        num_processes, 
        f0_method, 
        has_pitch_guidance, 
        model_name, 
        version, 
        crepe_hop_length
    )
    execute_generator_function(generator)
    print("Mangio-RVC-Fork Extração de recursos: Finalizado")

def cli_train(com):
    com = cli_split_command(com)
    model_name = com[0]
    sample_rate = com[1]
    has_pitch_guidance = True if (int(com[2]) == 1) else False
    speaker_id = int(com[3])
    save_epoch_iteration = int(com[4])
    total_epoch = int(com[5]) # 10000
    batch_size = int(com[6])
    gpu_card_slot_numbers = com[7]
    if_save_latest = i18n("是") if (int(com[8]) == 1) else i18n("否")
    if_cache_gpu = i18n("是") if (int(com[9]) == 1) else i18n("否")
    if_save_every_weight = i18n("是") if (int(com[10]) == 1) else i18n("否")
    version = com[11]

    pretrained_base = "pretrained/" if version == "v1" else "pretrained_v2/" 
    
    g_pretrained_path = "%sf0G%s.pth" % (pretrained_base, sample_rate)
    d_pretrained_path = "%sf0D%s.pth" % (pretrained_base, sample_rate)

    print("Mangio-RVC-Fork Train-CLI: Treinando...")
    click_train(
        model_name,
        sample_rate,
        has_pitch_guidance,
        speaker_id,
        save_epoch_iteration,
        total_epoch,
        batch_size,
        if_save_latest,
        g_pretrained_path,
        d_pretrained_path,
        gpu_card_slot_numbers,
        if_cache_gpu,
        if_save_every_weight,
        version
    )

def cli_train_feature(com):
    com = cli_split_command(com)
    model_name = com[0]
    version = com[1]
    print("Mangio-RVC-Fork Train Feature Index-CLI: Treinando...aguarde")
    generator = train_index(
        model_name,
        version
    )
    execute_generator_function(generator)
    print("Mangio-RVC-Fork Train Feature Index-CLI: Pronto!")

def cli_extract_model(com):
    com = cli_split_command(com)
    model_path = com[0]
    save_name = com[1]
    sample_rate = com[2]
    has_pitch_guidance = com[3]
    info = com[4]
    version = com[5]
    extract_small_model_process = extract_small_model(
        model_path,
        save_name,
        sample_rate,
        has_pitch_guidance,
        info,
        version
    )
    if extract_small_model_process == "Sucesso!":
        print("Mangio-RVC-Fork Extract Small Model: Sucesso!")
    else:
        print(str(extract_small_model_process))        
        print("Mangio-RVC-Fork Extract Small Model: Falhou!")

def print_page_details():
    if cli_current_page == "HOME":
        print("    go home            : Takes you back to home with a navigation list.")
        print("    go infer           : Takes you to inference command execution.\n")
        print("    go pre-process     : Takes you to training step.1) pre-process command execution.")
        print("    go extract-feature : Takes you to training step.2) extract-feature command execution.")
        print("    go train           : Takes you to training step.3) being or continue training command execution.")
        print("    go train-feature   : Takes you to the train feature index command execution.\n")
        print("    go extract-model   : Takes you to the extract small model command execution.")
    elif cli_current_page == "INFER":
        print("    arg 1) model name with .pth in ./weights: mi-test.pth")
        print("    arg 2) source audio path: myFolder\\MySource.wav")
        print("    arg 3) output file name to be placed in './audio-outputs': MyTest.wav")
        print("    arg 4) feature index file path: logs/mi-test/added_IVF3042_Flat_nprobe_1.index")
        print("    arg 5) speaker id: 0")
        print("    arg 6) transposition: 0")
        print("    arg 7) f0 method: harvest (pm, harvest, crepe, crepe-tiny, hybrid[x,x,x,x], mangio-crepe, mangio-crepe-tiny)")
        print("    arg 8) crepe hop length: 160")
        print("    arg 9) harvest median filter radius: 3 (0-7)")
        print("    arg 10) post resample rate: 0")
        print("    arg 11) mix volume envelope: 1")
        print("    arg 12) feature index ratio: 0.78 (0-1)")
        print("    arg 13) Voiceless Consonant Protection (Less Artifact): 0.33 (Smaller number = more protection. 0.50 means Dont Use.) \n")
        print("Example: mi-test.pth saudio/Sidney.wav myTest.wav logs/mi-test/added_index.index 0 -2 harvest 160 3 0 1 0.95 0.33")
    elif cli_current_page == "PRE-PROCESS":
        print("    arg 1) Model folder name in ./logs: mi-test")
        print("    arg 2) Trainset directory: mydataset (or) E:\\my-data-set")
        print("    arg 3) Sample rate: 40k (32k, 40k, 48k)")
        print("    arg 4) Number of CPU threads to use: 8 \n")
        print("Example: mi-test mydataset 40k 24")
    elif cli_current_page == "EXTRACT-FEATURE":
        print("    arg 1) Model folder name in ./logs: mi-test")
        print("    arg 2) Gpu card slot: 0 (0-1-2 if using 3 GPUs)")
        print("    arg 3) Number of CPU threads to use: 8")
        print("    arg 4) Has Pitch Guidance?: 1 (0 for no, 1 for yes)")
        print("    arg 5) f0 Method: harvest (pm, harvest, dio, crepe)")
        print("    arg 6) Crepe hop length: 128")
        print("    arg 7) Version for pre-trained models: v2 (use either v1 or v2)\n")
        print("Example: mi-test 0 24 1 harvest 128 v2")
    elif cli_current_page == "TRAIN":
        print("    arg 1) Model folder name in ./logs: mi-test")
        print("    arg 2) Sample rate: 40k (32k, 40k, 48k)")
        print("    arg 3) Has Pitch Guidance?: 1 (0 for no, 1 for yes)")
        print("    arg 4) speaker id: 0")
        print("    arg 5) Save epoch iteration: 50")
        print("    arg 6) Total epochs: 10000")
        print("    arg 7) Batch size: 8")
        print("    arg 8) Gpu card slot: 0 (0-1-2 if using 3 GPUs)")
        print("    arg 9) Save only the latest checkpoint: 0 (0 for no, 1 for yes)")
        print("    arg 10) Whether to cache training set to vram: 0 (0 for no, 1 for yes)")
        print("    arg 11) Save extracted small model every generation?: 0 (0 for no, 1 for yes)")
        print("    arg 12) Model architecture version: v2 (use either v1 or v2)\n")
        print("Example: mi-test 40k 1 0 50 10000 8 0 0 0 0 v2")
    elif cli_current_page == "TRAIN-FEATURE":
        print("    arg 1) Model folder name in ./logs: mi-test")
        print("    arg 2) Model architecture version: v2 (use either v1 or v2)\n")
        print("Example: mi-test v2")
    elif cli_current_page == "EXTRACT-MODEL":
        print("    arg 1) Model Path: logs/mi-test/G_168000.pth")
        print("    arg 2) Model save name: MyModel")
        print("    arg 3) Sample rate: 40k (32k, 40k, 48k)")
        print("    arg 4) Has Pitch Guidance?: 1 (0 for no, 1 for yes)")
        print('    arg 5) Model information: "My Model"')
        print("    arg 6) Model architecture version: v2 (use either v1 or v2)\n")
        print('Example: logs/mi-test/G_168000.pth MyModel 40k 1 "Criado por Cole Mangio" v2')
    print("")

def change_page(page):
    global cli_current_page
    cli_current_page = page
    return 0

def execute_command(com):
    if com == "go home":
        return change_page("HOME")
    elif com == "go infer":
        return change_page("INFER")
    elif com == "go pre-process":
        return change_page("PRE-PROCESS")
    elif com == "go extract-feature":
        return change_page("EXTRACT-FEATURE")
    elif com == "go train":
        return change_page("TRAIN")
    elif com == "go train-feature":
        return change_page("TRAIN-FEATURE")
    elif com == "go extract-model":
        return change_page("EXTRACT-MODEL")
    else:
        if com[:3] == "go ":
            print("page '%s' não existe!" % com[3:])
            return 0
    
    if cli_current_page == "INFER":
        cli_infer(com)
    elif cli_current_page == "PRE-PROCESS":
        cli_pre_process(com)
    elif cli_current_page == "EXTRACT-FEATURE":
        cli_extract_feature(com)
    elif cli_current_page == "TRAIN":
        cli_train(com)
    elif cli_current_page == "TRAIN-FEATURE":
        cli_train_feature(com)
    elif cli_current_page == "EXTRACT-MODEL":
        cli_extract_model(com)

def cli_navigation_loop():
    while True:
        print("Você atualmente esta em:  '%s':" % cli_current_page)
        print_page_details()
        command = input("%s: " % cli_current_page)
        try:
            execute_command(command)
        except:
            print(traceback.format_exc())

if(config.is_cli):
    print("\n\nMangio-RVC-Fork v2 CLI!\n")
    print("Bem vindo a versão CLI do RVC. Leia a documentação em https://github.com/Mangio621/Mangio-RVC-Fork (README.MD) para entender como funciona essa aplicação.\n")
    cli_navigation_loop()

#endregion

#region RVC WebUI App

def get_presets():
    data = None
    with open('../inference-presets.json', 'r') as file:
        data = json.load(file)
    preset_names = []
    for preset in data['presets']:
        preset_names.append(preset['name'])
    
    return preset_names

def change_choices2():
    audio_files=[]
    for filename in os.listdir("./audios"):
        if filename.endswith(('.wav','.mp3')):
            audio_files.append(os.path.join('./audios',filename))
    return {"choices": sorted(audio_files), "__type__": "update"}, {"__type__": "update"}
    
audio_files=[]
for filename in os.listdir("./audios"):
    if filename.endswith(('.wav','.mp3')):
        audio_files.append(os.path.join('./audios',filename))
        
def get_index():
    if check_for_name() != '':
        chosen_model=sorted(names)[0].split(".")[0]
        logs_path="./logs/"+chosen_model
        if os.path.exists(logs_path):
            for file in os.listdir(logs_path):
                if file.endswith(".index"):
                    return os.path.join(logs_path, file)
            return ''
        else:
            return ''
        
def get_indexes():
    indexes_list=[]
    for dirpath, dirnames, filenames in os.walk("./logs/"):
        for filename in filenames:
            if filename.endswith(".index"):
                indexes_list.append(os.path.join(dirpath,filename))
    if len(indexes_list) > 0:
        return indexes_list
    else:
        return ''
        
def get_name():
    if len(audio_files) > 0:
        return sorted(audio_files)[0]
    else:
        return ''
        
def save_to_wav(record_button):
    if record_button is None:
        pass
    else:
        path_to_file=record_button
        new_name = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")+'.wav'
        new_path='./audios/'+new_name
        shutil.move(path_to_file,new_path)
        return new_path
    
def save_to_wav2(dropbox):
    file_path=dropbox.name
    shutil.move(file_path,'./audios')
    return os.path.join('./audios',os.path.basename(file_path))
    
def match_index(sid0):
    folder=sid0.split(".")[0]
    parent_dir="./logs/"+folder
    if os.path.exists(parent_dir):
        for filename in os.listdir(parent_dir):
            if filename.endswith(".index"):
                index_path=os.path.join(parent_dir,filename)
                return index_path
    else:
        return ''
                
def check_for_name():
    if len(names) > 0:
        return sorted(names)[0]
    else:
        return ''
            
def download_from_url(url, model):
    if url == '':
        return "URL não pode estar vazio."
    if model =='':
        return "Nomeie seu modelo. Ex: 'nomemodelo'"
    url = url.strip()
    zip_dirs = ["zips", "unzips"]
    for directory in zip_dirs:
        if os.path.exists(directory):
            shutil.rmtree(directory)
    os.makedirs("zips", exist_ok=True)
    os.makedirs("unzips", exist_ok=True)
    zipfile = model + '.zip'
    zipfile_path = './zips/' + zipfile
    try:
        if "drive.google.com" in url:
            subprocess.run(["gdown", url, "--fuzzy", "-O", zipfile_path])
        elif "mega.nz" in url:
            m = Mega()
            m.download_url(url, './zips')
        else:
            subprocess.run(["wget", url, "-O", zipfile_path])
        for filename in os.listdir("./zips"):
            if filename.endswith(".zip"):
                zipfile_path = os.path.join("./zips/",filename)
                shutil.unpack_archive(zipfile_path, "./unzips", 'zip')
            else:
                return "No zipfile found."
        for root, dirs, files in os.walk('./unzips'):
            for file in files:
                file_path = os.path.join(root, file)
                if file.endswith(".index"):
                    os.mkdir(f'./logs/{model}')
                    shutil.copy2(file_path,f'./logs/{model}')
                elif "G_" not in file and "D_" not in file and file.endswith(".pth"):
                    shutil.copy(file_path,f'./weights/{model}.pth')
        shutil.rmtree("zips")
        shutil.rmtree("unzips")
        return "Success."
    except:
        return "There's been an error."
def success_message(face):
    return f'{face.name} has been uploaded.', 'None'
def mouth(size, face, voice, faces):
    if size == 'Half':
        size = 2
    else:
        size = 1
    if faces == 'None':
        character = face.name
    else:
        if faces == 'Ben Shapiro':
            character = '/content/wav2lip-HD/inputs/ben-shapiro-10.mp4'
        elif faces == 'Andrew Tate':
            character = '/content/wav2lip-HD/inputs/tate-7.mp4'
    command = "python inference.py " \
            "--checkpoint_path checkpoints/wav2lip.pth " \
            f"--face {character} " \
            f"--audio {voice} " \
            "--pads 0 20 0 0 " \
            "--outfile /content/wav2lip-HD/outputs/result.mp4 " \
            "--fps 24 " \
            f"--resize_factor {size}"
    process = subprocess.Popen(command, shell=True, cwd='/content/wav2lip-HD/Wav2Lip-master')
    stdout, stderr = process.communicate()
    return '/content/wav2lip-HD/outputs/result.mp4', 'Animação concluida.'
eleven_voices = ['Adam','Antoni','Josh','Arnold','Sam','Bella','Rachel','Domi','Elli']
eleven_voices_ids=['pNInz6obpgDQGcFmaJgB','ErXwobaYiN019PkySvjV','TxGEqnHWrfWFTfGW9XjX','VR6AewLTigWG4xSOukaG','yoZ06aMxZJJ28mfd3POQ','EXAVITQu4vr4xnSDxMaL','21m00Tcm4TlvDq8ikWAM','AZnzlk1XvdvUeBnXmlld','MF3mGyEYCl7XYWbV9V6O']
chosen_voice = dict(zip(eleven_voices, eleven_voices_ids))
def elevenTTS(xiapi, text, id, lang):
    if xiapi!= '' and id !='': 
        choice = chosen_voice[id]
        CHUNK_SIZE = 1024
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{choice}"
        headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": xiapi
        }
        if lang == 'en':
            data = {
            "text": text,
            "model_id": "eleven_monolingual_v1",
            "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.5
            }
            }
        else:
            data = {
            "text": text,
            "model_id": "eleven_multilingual_v1",
            "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.5
            }
            }

        response = requests.post(url, json=data, headers=headers)
        with open('./temp_eleven.mp3', 'wb') as f:
          for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
              if chunk:
                  f.write(chunk)
        aud_path = save_to_wav('./temp_eleven.mp3')
        return aud_path, aud_path
    else:
        tts = gTTS(text, lang=lang)
        tts.save('./temp_gTTS.mp3')
        aud_path = save_to_wav('./temp_gTTS.mp3')
        return aud_path, aud_path

def upload_to_dataset(files, dir):
    if dir == '':
        dir = './dataset'
    if not os.path.exists(dir):
        os.makedirs(dir)
    count = 0
    for file in files:
        path=file.name
        shutil.copy2(path,dir)
        count += 1
    return f' {count} files uploaded to {dir}.'     
    
def zip_downloader(model):
    if not os.path.exists(f'./weights/{model}.pth'):
        return {"__type__": "update"}, f'Confira se o nome da voz esta correto, não foi entrando {model}.pth'
    index_found = False
    for file in os.listdir(f'./logs/{model}'):
        if file.endswith('.index') and 'added' in file:
            log_file = file
            index_found = True
    if index_found:
        return [f'./weights/{model}.pth', f'./logs/{model}/{log_file}'], "Pronto."
    else:
        return f'./weights/{model}.pth', "Não foi encontrado index."

with gr.Blocks(theme=gr.themes.Base()) as app:
    with gr.Tabs():
        with gr.TabItem("Inference"):
            gr.HTML("<h1> Easy GUI v2 (rejekts) - adapatado para Mangio-RVC-Fork 💻 Traduzido por MrM0dZ | Junte-se a comunidade AI HUB Brasil </h1>")
            # Inference Preset Row
            # with gr.Row():
            #     mangio_preset = gr.Dropdown(label="Inference Preset", choices=sorted(get_presets()))
            #     mangio_preset_name_save = gr.Textbox(
            #         label="Your preset name"
            #     )
            #     mangio_preset_save_btn = gr.Button('Save Preset', variant="primary")

            # Other RVC stuff
            with gr.Row():
                sid0 = gr.Dropdown(label="1.Selecione seu modelo.", choices=sorted(names), value=check_for_name())
                refresh_button = gr.Button("Atualizar", variant="primary")
                if check_for_name() != '':
                    get_vc(sorted(names)[0])
                vc_transform0 = gr.Number(label="Mude o pitch aqui. Se a voz for do mesmo sexo não é necessario alterar. (12 caso seja Masculino para feminino, -12 caso seja o contrario.)", value=0)
                #clean_button = gr.Button(i18n("卸载音色省显存"), variant="primary")
                spk_item = gr.Slider(
                    minimum=0,
                    maximum=2333,
                    step=1,
                    label=i18n("Selecione o ID do alto-falante"),
                    value=0,
                    visible=False,
                    interactive=True,
                )
                #clean_button.click(fn=clean, inputs=[], outputs=[sid0])
                sid0.change(
                    fn=get_vc,
                    inputs=[sid0],
                    outputs=[spk_item],
                )
                but0 = gr.Button("Converter", variant="primary")
            with gr.Row():
                with gr.Column():
                    with gr.Row():
                        dropbox = gr.File(label="Arraste um áudio aqui e aperte o botão de Atualizar")
                    with gr.Row():
                        record_button=gr.Audio(source="microphone", label="Ou grave um áudio", type="filepath")
                    with gr.Row():
                        input_audio0 = gr.Dropdown(
                            label="2.Escolha o áudio.",
                            value="./audios/um-audio.mp3",
                            choices=audio_files
                            )
                        dropbox.upload(fn=save_to_wav2, inputs=[dropbox], outputs=[input_audio0])
                        dropbox.upload(fn=change_choices2, inputs=[], outputs=[input_audio0])
                        refresh_button2 = gr.Button("Atualizar", variant="primary", size='sm')
                        record_button.change(fn=save_to_wav, inputs=[record_button], outputs=[input_audio0])
                        record_button.change(fn=change_choices2, inputs=[], outputs=[input_audio0])
                    with gr.Row():
                        with gr.Accordion('Texto para fala', open=False):
                            with gr.Column():
                                lang = gr.Radio(label='Chines e Japones não funcionam com ElevenLabs no momento..',choices=['en','es','fr','pt','zh-CN','de','hi','ja'], value='en')
                                api_box = gr.Textbox(label="Insira sua chave API do ElevenLabs, ou deixe vazio para usar o GoogleTTS", value='')
                                elevenid=gr.Dropdown(label="Voz:", choices=eleven_voices)
                            with gr.Column():
                                tfs = gr.Textbox(label="Insira um texto", interactive=True, value="Isso é um teste.")
                                tts_button = gr.Button(value="Falar")
                                tts_button.click(fn=elevenTTS, inputs=[api_box,tfs, elevenid, lang], outputs=[record_button, input_audio0])
                    with gr.Row():
                        with gr.Accordion('Wav2Lip', open=False):
                            with gr.Row():
                                size = gr.Radio(label='Resolution:',choices=['Half','Full'])
                                face = gr.UploadButton("Envie um personagem",type='file')
                                faces = gr.Dropdown(label="Ou escolha um:", choices=['None','Ben Shapiro','Andrew Tate'])
                            with gr.Row():
                                preview = gr.Textbox(label="Status:",interactive=False)
                                face.upload(fn=success_message,inputs=[face], outputs=[preview, faces])
                            with gr.Row():
                                animation = gr.Video(type='filepath')
                                refresh_button2.click(fn=change_choices2, inputs=[], outputs=[input_audio0, animation])
                            with gr.Row():
                                animate_button = gr.Button('Animar')

                with gr.Column():
                    with gr.Accordion("Index Settings", open=False):
                        file_index1 = gr.Dropdown(
                            label="3. Caminho para o index. (Caso não tenha sido encontrado automatico)",
                            choices=get_indexes(),
                            value=get_index(),
                            interactive=True,
                            )
                        sid0.change(fn=match_index, inputs=[sid0],outputs=[file_index1])
                        refresh_button.click(
                            fn=change_choices, inputs=[], outputs=[sid0, file_index1]
                            )
                        # file_big_npy1 = gr.Textbox(
                        #     label=i18n("特征文件路径"),
                        #     value="E:\\codes\py39\\vits_vc_gpu_train\\logs\\mi-test-1key\\total_fea.npy",
                        #     interactive=True,
                        # )
                        index_rate1 = gr.Slider(
                            minimum=0,
                            maximum=1,
                            label=i18n("Taxa de recurso de recuperação"),
                            value=0.66,
                            interactive=True,
                            )
                    vc_output2 = gr.Audio(label="Saido de Audio (Clique nos 3 pontinhos do lado direito para baixar)",type='filepath')
                    animate_button.click(fn=mouth, inputs=[size, face, vc_output2, faces], outputs=[animation, preview])
                    with gr.Accordion("Advanced Settings", open=False):
                        f0method0 = gr.Radio(
                            label="Opcional: Mude o algoritmo de pitch",
                            choices=["pm", "dio", "mangio-crepe-tiny", "crepe-tiny", "crepe", "mangio-crepe", "harvest","rmvpe"], # Fork Feature. Add Crepe-Tiny
                            value="mangio-crepe",
                            interactive=True,
                        )
                        crepe_hop_length = gr.Slider(
                            minimum=1,
                            maximum=512,
                            step=1,
                            label="Mangio-Crepe Hop Length. Numeros maiores vão reduzir mudanças de pitch. Mas reduzir precisão.",
                            value=120,
                            interactive=True
                            )
                        filter_radius0 = gr.Slider(
                            minimum=0,
                            maximum=7,
                            label=i18n(">=3, use o filtro mediano para o resultado do reconhecimento do tom do 'harvest'"),
                            value=3,
                            step=1,
                            interactive=True,
                            )
                        resample_sr0 = gr.Slider(
                            minimum=0,
                            maximum=48000,
                            label=i18n("Reamostragem pós-processamento para a taxa de amostragem final, 0 anula."),
                            value=0,
                            step=1,
                            interactive=True,
                            visible=False
                            )
                        rms_mix_rate0 = gr.Slider(
                            minimum=0,
                            maximum=1,
                            label=i18n("O volume da fonte de entrada substitui a taxa de fusão do volume de saída, quanto mais próximo de 1, mais o envelope de saída é usado"),
                            value=0.21,
                            interactive=True,
                            )
                        protect0 = gr.Slider(
                            minimum=0,
                            maximum=0.5,
                            label=i18n("O volume da fonte de entrada substitui a taxa de fusão do volume de saída, quanto mais próximo de 1, mais o envelope de saída é usado"),
                            value=0.33,
                            step=0.01,
                            interactive=True,
                            )
            with gr.Row():
                vc_output1 = gr.Textbox("")
                f0_file = gr.File(label=i18n("Opicional: Arquivo de curva F0, um passo por linha, em vez do padrão F0 e altos e baixos"), visible=False)
                
                but0.click(
                    vc_single,
                    [
                        spk_item,
                        input_audio0,
                        vc_transform0,
                        f0_file,
                        f0method0,
                        file_index1,
                        # file_index2,
                        # file_big_npy1,
                        index_rate1,
                        filter_radius0,
                        resample_sr0,
                        rms_mix_rate0,
                        protect0,
                        crepe_hop_length
                    ],
                    [vc_output1, vc_output2],
                )
                        
            with gr.Accordion("Conversão em fila",open=False):
                with gr.Row():
                    with gr.Column():
                        vc_transform1 = gr.Number(
                            label=i18n("Alterar Pitch: 12 para vozes femininas, -12 para vozes masculinas)"), value=0
                        )
                        opt_input = gr.Textbox(label=i18n("Especifique a pasta de saída"), value="opt")
                        f0method1 = gr.Radio(
                            label=i18n(
                                "Selecione o algoritmo de extração de pitch, de preferencia utilize o crepe ou harvest."
                            ),
                            choices=["pm", "harvest", "crepe"],
                            value="pm",
                            interactive=True,
                        )
                        filter_radius1 = gr.Slider(
                            minimum=0,
                            maximum=7,
                            label=i18n(">=3, use o filtro mediano para o resultado do reconhecimento do tom do 'harvest'"),
                            value=3,
                            step=1,
                            interactive=True,
                        )
                    with gr.Column():
                        file_index3 = gr.Textbox(
                            label=i18n("Caminho do arquivo da biblioteca de recuperação de recursos."),
                            value="",
                            interactive=True,
                        )
                        file_index4 = gr.Dropdown(
                            label=i18n("Detectar automaticamente o caminho do índice"),
                            choices=sorted(index_paths),
                            interactive=True,
                        )
                        refresh_button.click(
                            fn=lambda: change_choices()[1],
                            inputs=[],
                            outputs=file_index4,
                        )
                        # file_big_npy2 = gr.Textbox(
                        #     label=i18n("特征文件路径"),
                        #     value="E:\\codes\\py39\\vits_vc_gpu_train\\logs\\mi-test-1key\\total_fea.npy",
                        #     interactive=True,
                        # )
                        index_rate2 = gr.Slider(
                            minimum=0,
                            maximum=1,
                            label=i18n("Detectar automaticamente o caminho do índice, seleção suspensa (suspenso)"),
                            value=1,
                            interactive=True,
                        )
                    with gr.Column():
                        resample_sr1 = gr.Slider(
                            minimum=0,
                            maximum=48000,
                            label=i18n("Reamostragem pós-processamento para a taxa de amostragem final, 0 significa sem reamostragem"),
                            value=0,
                            step=1,
                            interactive=True,
                        )
                        rms_mix_rate1 = gr.Slider(
                            minimum=0,
                            maximum=1,
                            label=i18n("O volume da fonte de entrada substitui a taxa de fusão do volume de saída, quanto mais próximo de 1, mais o envelope de saída é usado"),
                            value=1,
                            interactive=True,
                        )
                        protect1 = gr.Slider(
                            minimum=0,
                            maximum=0.5,
                            label=i18n(
                                "Proteja consoantes sem voz e sons respiratórios, evite artefatos como quebra de som eletrônico e desligue-o quando estiver cheio de 0,5. Diminua-o para aumentar a proteção, mas pode reduzir o efeito de indexação"
                            ),
                            value=0.33,
                            step=0.01,
                            interactive=True,
                        )
                    with gr.Column():
                        dir_input = gr.Textbox(
                            label=i18n("Digite o caminho da pasta de áudio a ser processada (basta ir até a barra de endereços do gerenciador de arquivos e copiá-la))"),
                            value="E:\codes\varios-arquivos",
                        )
                        inputs = gr.File(
                            file_count="multiple", label=i18n("Você também pode inserir arquivos de áudio em lotes, escolher um dos dois e ler a pasta primeiro")
                        )
                    with gr.Row():
                        format1 = gr.Radio(
                            label=i18n("Escolha o formato de arquivo desejado.),
                            choices=["wav", "flac", "mp3", "m4a"],
                            value="flac",
                            interactive=True,
                        )
                        but1 = gr.Button(i18n("Converter"), variant="primary")
                        vc_output3 = gr.Textbox(label=i18n("Informações de saida"))
                    but1.click(
                        vc_multi,
                        [
                            spk_item,
                            dir_input,
                            opt_input,
                            inputs,
                            vc_transform1,
                            f0method1,
                            file_index3,
                            file_index4,
                            # file_big_npy2,
                            index_rate2,
                            filter_radius1,
                            resample_sr1,
                            rms_mix_rate1,
                            protect1,
                            format1,
                            crepe_hop_length,
                        ],
                        [vc_output3],
                    )
                    but1.click(fn=lambda: easy_uploader.clear())
        with gr.TabItem("Baixar Modelo"):
            with gr.Row():
                url=gr.Textbox(label="Insira a URL do modelo.:")
            with gr.Row():
                model = gr.Textbox(label="Nomeie seu modelo:")
                download_button=gr.Button("Download")
            with gr.Row():
                status_bar=gr.Textbox(label="")
                download_button.click(fn=download_from_url, inputs=[url, model], outputs=[status_bar])
            with gr.Row():
                gr.Markdown(
                """
                Original RVC:https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI
                Mangio's RVC Fork:https://github.com/Mangio621/Mangio-RVC-Fork
                ❤️ Se quiser apoiar o autor do EasyGui.❤️ 
                https://paypal.me/lesantillan
                ❤️ Apoie nossa tradução! Você pode fazer uma doação no PIX: aihubbrasil@gmail.com ❤️ 
                
                """
                )
                
        with gr.TabItem("Treinar", visible=False):
            with gr.Row():
                with gr.Column():
                    exp_dir1 = gr.Textbox(label="Nome:", value="Meu-modelo")
                    sr2 = gr.Radio(
                        label=i18n("Taxa de amostragem alvo"),
                        choices=["40k", "48k"],
                        value="40k",
                        interactive=True,
                        visible=False
                    )
                    if_f0_3 = gr.Radio(
                        label=i18n("O modelo tem orientação de tom. (Para canto deve ter, falar não)"),
                        choices=[True, False],
                        value=True,
                        interactive=True,
                        visible=False
                    )
                    version19 = gr.Radio(
                        label="Versão RVC",
                        choices=["v1", "v2"],
                        value="v2",
                        interactive=True,
                        visible=False,
                    )
                    np7 = gr.Slider(
                        minimum=0,
                        maximum=config.n_cpu,
                        step=1,
                        label="# de CPUs para processar.(Não altere.)",
                        value=config.n_cpu,
                        interactive=True,
                        visible=True
                    )
                    trainset_dir4 = gr.Textbox(label="Caminho para seu dataset (audios, não o zip):", value="./dataset")
                    easy_uploader = gr.Files(label='Envie seu áudios aqui. Eles vão ser enviados para pasta acima.',file_types=['audio'])
                    but1 = gr.Button("1. Processar dataset", variant="primary")
                    info1 = gr.Textbox(label="Status (espere até aparecer 'end preprocess'):", value="")
                    easy_uploader.upload(fn=upload_to_dataset, inputs=[easy_uploader, trainset_dir4], outputs=[info1])
                    but1.click(
                        preprocess_dataset, [trainset_dir4, exp_dir1, sr2, np7], [info1]
                    )
                with gr.Column():
                    spk_id5 = gr.Slider(
                        minimum=0,
                        maximum=4,
                        step=1,
                        label=i18n("Identificar ID da voz"),
                        value=0,
                        interactive=True,
                        visible=False
                    )
                    with gr.Accordion('Configurações da GPU', open=False, visible=False):
                        gpus6 = gr.Textbox(
                            label=i18n("Mantenha em 0"),
                            value=gpus,
                            interactive=True,
                            visible=False
                        )
                        gpu_info9 = gr.Textbox(label=i18n("Informações sobre a GPU"), value=gpu_info)
                    f0method8 = gr.Radio(
                        label=i18n(
                            "Selecione o algoritmo de extração de voz. (mangio-crepe é o melhor atualmente.)"
                        ),
                        choices=["harvest","crepe", "mangio-crepe"], # Fork feature: Crepe on f0 extraction for training.
                        value="mangio-crepe",
                        interactive=True,
                    )
                    extraction_crepe_hop_length = gr.Slider(
                        minimum=1,
                        maximum=512,
                        step=1,
                        label=i18n("crepe_hop_length"),
                        value=128,
                        interactive=True
                    )
                    but2 = gr.Button("2.Extração de pitch", variant="primary")
                    info2 = gr.Textbox(label="Status(Confira o console do colab):", value="", max_lines=8)
                    but2.click(
                            extract_f0_feature,
                            [gpus6, np7, f0method8, if_f0_3, exp_dir1, version19, extraction_crepe_hop_length],
                            [info2],
                        )
                with gr.Row():      
                    with gr.Column():
                        total_epoch11 = gr.Slider(
                            minimum=0,
                            maximum=10000,
                            step=10,
                            label="Numero de Epochs. (Recomendo 100 por cada 5 minutos de dataset):",
                            value=250,
                            interactive=True,
                        )
                        but3 = gr.Button("3.Treinar modelo.", variant="primary")
                        but4 = gr.Button("4.Treinar index", variant="primary")
                        info3 = gr.Textbox(label="Status(Confira o console do colab):", value="", max_lines=10)
                        with gr.Accordion("Preferencias de treino. (Pode deixar padrão)", open=False):
                            #gr.Markdown(value=i18n("step3: 填写训练设置, 开始训练模型和索引"))
                            with gr.Column():
                                save_epoch10 = gr.Slider(
                                    minimum=0,
                                    maximum=100,
                                    step=5,
                                    label="Backup a cada # epochs:",
                                    value=25,
                                    interactive=True,
                                )
                                batch_size12 = gr.Slider(
                                    minimum=1,
                                    maximum=40,
                                    step=1,
                                    label="Batch Size (Mantenha em 20 no colab!):",
                                    value=default_batch_size,
                                    interactive=True,
                                )
                                if_save_latest13 = gr.Radio(
                                    label=i18n("Salvar apenas o arquivo ckpt mais recente para economizar espaço no drive.),
                                    choices=[i18n("Sim"), i18n("Não")],
                                    value=i18n("Sim"),
                                    interactive=True,
                                )
                                if_cache_gpu17 = gr.Radio(
                                    label=i18n(
                                        "Armazenar em cache todos os conjuntos de treinamento na memória de vídeo. Datasets com menos de 10 minutos podem ser armazenados em cache para acelerar o treinamento, e um cache de dados grande irá exceder a memória de vídeo e não aumentar muito a velocidade"
                                    ),
                                    choices=[i18n("Sim"), i18n("Não")],
                                    value=i18n("Não"),
                                    interactive=True,
                                )
                                if_save_every_weights18 = gr.Radio(
                                    label=i18n("Salve um modelo na pasta 'weights' a cada backup:"),
                                    choices=[i18n("Sim"), i18n("Não")],
                                    value=i18n("Sim"),
                                    interactive=True,
                                )
                        zip_model = gr.Button('5. Baixar modelo.')
                        zipped_model = gr.Files(label='Seu modelo e index podem ser baixados aqui:')
                        zip_model.click(fn=zip_downloader, inputs=[exp_dir1], outputs=[zipped_model, info3])
            with gr.Group():
                with gr.Accordion("Modelos bases:", open=False, visible=False):
                    pretrained_G14 = gr.Textbox(
                        label=i18n("Carregando modelo f0G40k"),
                        value="pretrained_v2/f0G40k.pth",
                        interactive=True,
                    )
                    pretrained_D15 = gr.Textbox(
                        label=i18n("Carregando modelo f0D40K"),
                        value="pretrained_v2/f0D40k.pth",
                        interactive=True,
                    )
                    gpus16 = gr.Textbox(
                        label=i18n("Mantenha em 0"),
                        value=gpus,
                        interactive=True,
                    )
                sr2.change(
                    change_sr2,
                    [sr2, if_f0_3, version19],
                    [pretrained_G14, pretrained_D15, version19],
                )
                version19.change(
                    change_version19,
                    [sr2, if_f0_3, version19],
                    [pretrained_G14, pretrained_D15],
                )
                if_f0_3.change(
                    change_f0,
                    [if_f0_3, sr2, version19],
                    [f0method8, pretrained_G14, pretrained_D15],
                )
                but5 = gr.Button(i18n("Treinamento chave"), variant="primary", visible=False)
                but3.click(
                    click_train,
                    [
                        exp_dir1,
                        sr2,
                        if_f0_3,
                        spk_id5,
                        save_epoch10,
                        total_epoch11,
                        batch_size12,
                        if_save_latest13,
                        pretrained_G14,
                        pretrained_D15,
                        gpus16,
                        if_cache_gpu17,
                        if_save_every_weights18,
                        version19,
                    ],
                    info3,
                )
                but4.click(train_index, [exp_dir1, version19], info3)
                but5.click(
                    train1key,
                    [
                        exp_dir1,
                        sr2,
                        if_f0_3,
                        trainset_dir4,
                        spk_id5,
                        np7,
                        f0method8,
                        save_epoch10,
                        total_epoch11,
                        batch_size12,
                        if_save_latest13,
                        pretrained_G14,
                        pretrained_D15,
                        gpus16,
                        if_cache_gpu17,
                        if_save_every_weights18,
                        version19,
                        extraction_crepe_hop_length
                    ],
                    info3,
                )


            try:
                if tab_faq == "FAQ":
                    with open("docs/faq.md", "r", encoding="utf8") as f:
                        info = f.read()
                else:
                    with open("docs/faq_en.md", "r", encoding="utf8") as f:
                        info = f.read()
                gr.Markdown(value=info)
            except:
                gr.Markdown("")


    #region Mangio Preset Handler Region
    def save_preset(preset_name,sid0,vc_transform,input_audio,f0method,crepe_hop_length,filter_radius,file_index1,file_index2,index_rate,resample_sr,rms_mix_rate,protect,f0_file):
        data = None
        with open('../inference-presets.json', 'r') as file:
            data = json.load(file)
        preset_json = {
            'name': preset_name,
            'model': sid0,
            'transpose': vc_transform,
            'audio_file': input_audio,
            'f0_method': f0method,
            'crepe_hop_length': crepe_hop_length,
            'median_filtering': filter_radius,
            'feature_path': file_index1,
            'auto_feature_path': file_index2,
            'search_feature_ratio': index_rate,
            'resample': resample_sr,
            'volume_envelope': rms_mix_rate,
            'protect_voiceless': protect,
            'f0_file_path': f0_file
        }
        data['presets'].append(preset_json)
        with open('../inference-presets.json', 'w') as file:
            json.dump(data, file)
            file.flush()
        print("Preset salvo %s em inference-presets.json!" % preset_name)


    def on_preset_changed(preset_name):
        print("Preset alterado para %s!" % preset_name)
        data = None
        with open('../inference-presets.json', 'r') as file:
            data = json.load(file)

        print("Buscando por " + preset_name)
        returning_preset = None
        for preset in data['presets']:
            if(preset['name'] == preset_name):
                print("Preset encontrado")
                returning_preset = preset
        # return all new input values
        return (
            # returning_preset['model'],
            # returning_preset['transpose'],
            # returning_preset['audio_file'],
            # returning_preset['f0_method'],
            # returning_preset['crepe_hop_length'],
            # returning_preset['median_filtering'],
            # returning_preset['feature_path'],
            # returning_preset['auto_feature_path'],
            # returning_preset['search_feature_ratio'],
            # returning_preset['resample'],
            # returning_preset['volume_envelope'],
            # returning_preset['protect_voiceless'],
            # returning_preset['f0_file_path']
        )

    # Preset State Changes                
    
    # This click calls save_preset that saves the preset into inference-presets.json with the preset name
    # mangio_preset_save_btn.click(
    #     fn=save_preset, 
    #     inputs=[
    #         mangio_preset_name_save,
    #         sid0,
    #         vc_transform0,
    #         input_audio0,
    #         f0method0,
    #         crepe_hop_length,
    #         filter_radius0,
    #         file_index1,
    #         file_index2,
    #         index_rate1,
    #         resample_sr0,
    #         rms_mix_rate0,
    #         protect0,
    #         f0_file
    #     ], 
    #     outputs=[]
    # )

    # mangio_preset.change(
    #     on_preset_changed, 
    #     inputs=[
    #         # Pass inputs here
    #         mangio_preset
    #     ], 
    #     outputs=[
    #         # Pass Outputs here. These refer to the gradio elements that we want to directly change
    #         # sid0,
    #         # vc_transform0,
    #         # input_audio0,
    #         # f0method0,
    #         # crepe_hop_length,
    #         # filter_radius0,
    #         # file_index1,
    #         # file_index2,
    #         # index_rate1,
    #         # resample_sr0,
    #         # rms_mix_rate0,
    #         # protect0,
    #         # f0_file
    #     ]
    # )


        # with gr.TabItem(i18n("招募音高曲线前端编辑器")):
        #     gr.Markdown(value=i18n("加开发群联系我xxxxx"))
        # with gr.TabItem(i18n("点击查看交流、问题反馈群号")):
        #     gr.Markdown(value=i18n("xxxxx"))

                
    if config.iscolab or config.paperspace: # Share gradio link for colab and paperspace (FORK FEATURE)
        app.queue(concurrency_count=511, max_size=1022).launch(share=True, quiet=True)
    else:
        app.queue(concurrency_count=511, max_size=1022).launch(
            server_name="0.0.0.0",
            inbrowser=not config.noautoopen,
            server_port=config.listen_port,
            quiet=True,
        )
