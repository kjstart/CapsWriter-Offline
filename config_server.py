"""兼容旧导入接口；所有用户设置来自根目录 config.json。"""
import os
from pathlib import Path
from settings import SETTINGS, BASE_DIR, resolve_model_paths
__version__ = '2.6'

class ServerConfig:
    addr = SETTINGS['server']['addr']
    port = SETTINGS['server']['port']
    model_type = SETTINGS['server']['model_type']
    format_num = SETTINGS['server']['format_num']
    format_spell = SETTINGS['server']['format_spell']
    enable_tray = SETTINGS['server']['enable_tray']
    hotwords_path = Path(SETTINGS['server']['hotwords_path'])
    log_level = SETTINGS['server']['log_level']
    aligner_idle_timeout = SETTINGS['server']['aligner_idle_timeout']
    gpu_boost_enabled = SETTINGS['server']['gpu_boost_enabled']
    gpu_boost_cmd = SETTINGS['server']['gpu_boost_cmd']
    gpu_unboost_cmd = SETTINGS['server']['gpu_unboost_cmd']
    gpu_unboost_timeout = SETTINGS['server']['gpu_unboost_timeout']

class ModelDownloadLinks:
    models_page = SETTINGS['model_downloads']['models_page']

ModelPaths = type('ModelPaths', (), resolve_model_paths(SETTINGS['model_paths']))

class ParaformerArgs:
    paraformer = ModelPaths.paraformer_model.as_posix()
    tokens = ModelPaths.paraformer_tokens.as_posix()
    num_threads = SETTINGS['paraformer']['num_threads']
    sample_rate = SETTINGS['paraformer']['sample_rate']
    feature_dim = SETTINGS['paraformer']['feature_dim']
    decoding_method = SETTINGS['paraformer']['decoding_method']
    provider = SETTINGS['paraformer']['provider']
    debug = SETTINGS['paraformer']['debug']

class SenseVoiceArgs:
    encoder_path = ModelPaths.sensevoice_encoder.as_posix()
    decoder_path = ModelPaths.sensevoice_decoder.as_posix()
    tokenizer_path = ModelPaths.sensevoice_tokenizer.as_posix()
    itn = SETTINGS['sensevoice']['itn']
    onnx_provider = SETTINGS['sensevoice']['onnx_provider']
    top_k = SETTINGS['sensevoice']['top_k']
    dml_pad_to = SETTINGS['sensevoice']['dml_pad_to']

class FunASRNanoGGUFArgs:
    encoder_onnx_path = ModelPaths.fun_asr_nano_gguf_encoder_adaptor.as_posix()
    ctc_onnx_path = ModelPaths.fun_asr_nano_gguf_ctc.as_posix()
    decoder_gguf_path = ModelPaths.fun_asr_nano_gguf_llm_decode.as_posix()
    tokens_path = ModelPaths.fun_asr_nano_gguf_token.as_posix()
    onnx_provider = SETTINGS['fun_asr_nano']['onnx_provider']
    llm_use_gpu = SETTINGS['fun_asr_nano']['llm_use_gpu']
    vulkan_force_fp32 = SETTINGS['fun_asr_nano']['vulkan_force_fp32']
    enable_ctc = SETTINGS['fun_asr_nano']['enable_ctc']
    n_predict = SETTINGS['fun_asr_nano']['n_predict']
    n_threads = SETTINGS['fun_asr_nano']['n_threads']
    similar_threshold = SETTINGS['fun_asr_nano']['similar_threshold']
    max_hotwords = SETTINGS['fun_asr_nano']['max_hotwords']
    dml_pad_to = SETTINGS['fun_asr_nano']['dml_pad_to']
    verbose = SETTINGS['fun_asr_nano']['verbose']

class Qwen3ASRGGUFArgs:
    model_dir = ModelPaths.qwen3_asr_gguf_dir.as_posix()
    encoder_frontend_fn = ModelPaths.qwen3_asr_gguf_encoder_frontend.name
    encoder_backend_fn = ModelPaths.qwen3_asr_gguf_encoder_backend.name
    llm_fn = ModelPaths.qwen3_asr_gguf_llm_decode.name
    onnx_provider = SETTINGS['qwen_asr']['onnx_provider']
    llm_use_gpu = SETTINGS['qwen_asr']['llm_use_gpu']
    n_ctx = SETTINGS['qwen_asr']['n_ctx']
    chunk_size = SETTINGS['qwen_asr']['chunk_size']
    memory_num = SETTINGS['qwen_asr']['memory_num']
    dml_pad_to = SETTINGS['qwen_asr']['dml_pad_to']
    verbose = SETTINGS['qwen_asr']['verbose']

class ForceAlignerGGUFArgs:
    model_dir = ModelPaths.force_aligner_gguf_dir.as_posix()
    encoder_frontend_fn = ModelPaths.force_aligner_gguf_encoder_frontend.name
    encoder_backend_fn = ModelPaths.force_aligner_gguf_encoder_backend.name
    llm_fn = ModelPaths.force_aligner_gguf_llm_decode.name
    onnx_provider = SETTINGS['force_aligner']['onnx_provider']
    llm_use_gpu = SETTINGS['force_aligner']['llm_use_gpu']
    n_ctx = SETTINGS['force_aligner']['n_ctx']
    dml_pad_to = SETTINGS['force_aligner']['dml_pad_to']
