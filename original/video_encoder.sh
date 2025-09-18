#!/bin/bash
# Advanced Video Encoder and Merger - Shell Script Version
# Supports hardware acceleration detection and multiple codecs

set -e

# Enable tab completion for file paths
if [ -n "$BASH_VERSION" ]; then
    # Enable readline for better tab completion
    set -o emacs
    bind 'set show-all-if-ambiguous on' 2>/dev/null || true
    bind 'set completion-ignore-case on' 2>/dev/null || true
    bind 'set menu-complete-display-prefix on' 2>/dev/null || true
fi

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
OUTPUT_FILE="merged_output.mp4"
PRESET="auto"
QUALITY="25"
EXTENSIONS="mp4 mkv avi mov wmv flv webm m4v"
MENU=false

# Function to print colored output
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check if a specific encoder is present in ffmpeg
has_encoder() {
    local enc="$1"
    ffmpeg -hide_banner -encoders 2>/dev/null | awk '{print $2}' | grep -Fxq "$enc"
}

# Check if an encoder actually works (not just present)
encoder_works() {
    local enc="$1"
    if ! has_encoder "$enc"; then
        return 1
    fi
    
    # Test with a simple 1-second video
    ffmpeg -f lavfi -i testsrc=duration=1:size=320x240:rate=1 -c:v "$enc" -f null - 2>/dev/null >/dev/null 2>&1
    return $?
}

# Function to install prerequisites
install_prerequisites() {
    print_info "Installing prerequisites..."
    
    # Update package list
    print_info "Updating package list..."
    sudo apt update
    
    # Install FFmpeg
    print_info "Installing FFmpeg..."
    sudo apt install -y ffmpeg
    
    # Install additional codecs and libraries
    print_info "Installing additional codecs and libraries..."
    sudo apt install -y \
        libx264-dev \
        libx265-dev \
        libaom-dev \
        libvpx-dev \
        libfdk-aac-dev \
        libmp3lame-dev \
        libopus-dev \
        libvorbis-dev \
        libtheora-dev \
        libxvidcore-dev \
        libx264-dev \
        libx265-dev
    
    # Install NVIDIA drivers and CUDA if available
    if command_exists nvidia-smi; then
        print_success "NVIDIA drivers already installed"
    else
        print_info "NVIDIA drivers not detected. To enable GPU acceleration:"
        echo "  sudo apt install nvidia-driver-470 nvidia-cuda-toolkit"
        echo "  # Then reboot your system"
    fi
    
    print_success "Prerequisites installation completed!"
}

# Function to detect hardware acceleration and test all encoders
detect_hardware() {
    print_info "Detecting hardware acceleration and testing encoders..."
    
    # Check FFmpeg
    if ! command_exists ffmpeg; then
        print_error "FFmpeg not found."
        print_info "Would you like to install prerequisites automatically? (y/n)"
        read -rp "> " install_choice
        
        case "$install_choice" in
            y|Y|yes|YES)
                install_prerequisites
                ;;
            *)
                print_error "Please install FFmpeg manually:"
                echo "  sudo apt install ffmpeg"
                exit 1
                ;;
        esac
    fi
    
    # Initialize encoder availability flags
    NVENC_AVAILABLE=false
    QSV_AVAILABLE=false
    VAAPI_AVAILABLE=false
    
    # Test NVIDIA NVENC encoders
    if encoder_works "h264_nvenc" || encoder_works "hevc_nvenc"; then
        NVENC_AVAILABLE=true
        print_success "NVIDIA NVENC detected"
    fi
    
    # Test Intel QSV encoders
    if encoder_works "h264_qsv" || encoder_works "hevc_qsv"; then
        QSV_AVAILABLE=true
        print_success "Intel QSV detected"
    fi
    
    # Test VA-API encoders
    if encoder_works "h264_vaapi" || encoder_works "hevc_vaapi"; then
        VAAPI_AVAILABLE=true
        print_success "VA-API detected"
    fi
    
    # Check for NVIDIA GPU
    if command_exists nvidia-smi; then
        GPU_INFO=$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits 2>/dev/null | head -1)
        if [ -n "$GPU_INFO" ]; then
            print_success "NVIDIA GPU: $GPU_INFO"
        fi
    fi
    
    # Test and cache all individual encoder availability
    print_info "Testing individual encoders..."
    
    # NVIDIA encoders
    if [ "$NVENC_AVAILABLE" = true ]; then
        if encoder_works "h264_nvenc"; then
            print_success "  h264_nvenc: ✓"
        else
            print_warning "  h264_nvenc: ✗"
        fi
        
        if encoder_works "hevc_nvenc"; then
            print_success "  hevc_nvenc: ✓"
        else
            print_warning "  hevc_nvenc: ✗"
        fi
        
        if encoder_works "av1_nvenc"; then
            print_success "  av1_nvenc: ✓"
        else
            print_warning "  av1_nvenc: ✗"
        fi
    fi
    
    # Intel QSV encoders
    if [ "$QSV_AVAILABLE" = true ]; then
        if encoder_works "h264_qsv"; then
            print_success "  h264_qsv: ✓"
        else
            print_warning "  h264_qsv: ✗"
        fi
        
        if encoder_works "hevc_qsv"; then
            print_success "  hevc_qsv: ✓"
        else
            print_warning "  hevc_qsv: ✗"
        fi
        
        if encoder_works "av1_qsv"; then
            print_success "  av1_qsv: ✓"
        else
            print_warning "  av1_qsv: ✗"
        fi
    fi
    
    # VA-API encoders
    if [ "$VAAPI_AVAILABLE" = true ]; then
        if encoder_works "h264_vaapi"; then
            print_success "  h264_vaapi: ✓"
        else
            print_warning "  h264_vaapi: ✗"
        fi
        
        if encoder_works "hevc_vaapi"; then
            print_success "  hevc_vaapi: ✓"
        else
            print_warning "  hevc_vaapi: ✗"
        fi
        
        if encoder_works "av1_vaapi"; then
            print_success "  av1_vaapi: ✓"
        else
            print_warning "  av1_vaapi: ✗"
        fi
    fi
    
    # CPU encoders (always available)
    if encoder_works "libx264"; then
        print_success "  libx264: ✓"
    else
        print_warning "  libx264: ✗"
    fi
    
    if encoder_works "libx265"; then
        print_success "  libx265: ✓"
    else
        print_warning "  libx265: ✗"
    fi
    
    if encoder_works "libaom-av1"; then
        print_success "  libaom-av1: ✓"
    else
        print_warning "  libaom-av1: ✗"
    fi
}

# Function to find video files
find_video_files() {
    local input_dir="$1"
    local files=()
    
    for ext in $EXTENSIONS; do
        while IFS= read -r -d '' file; do
            files+=("$file")
        done < <(find "$input_dir" -maxdepth 1 -name "*.$ext" -print0 2>/dev/null)
    done
    
    # Sort files naturally
    printf '%s\n' "${files[@]}" | sort -V
}

# Function to create file list
create_file_list() {
    local files=("$@")
    local list_file="filelist.txt"
    
    > "$list_file"
    for file in "${files[@]}"; do
        # Escape single quotes for FFmpeg
        escaped_file=$(echo "$file" | sed "s/'/'\"'\"'/g")
        echo "file '$escaped_file'" >> "$list_file"
    done
    
    echo "$list_file"
}

# Function to get video info
get_video_info() {
    local file="$1"
    ffprobe -v quiet -print_format json -show_format -show_streams "$file" 2>/dev/null | \
    jq -r '.streams[] | select(.codec_type=="video") | "\(.width)x\(.height) - \(.codec_name)"' | head -1
}

# Function to calculate total input file size
calculate_input_size() {
    local input_dir="$1"
    local total_size=0
    
    for ext in $EXTENSIONS; do
        while IFS= read -r -d '' file; do
            if [ -f "$file" ]; then
                local file_size=$(stat -c%s "$file" 2>/dev/null || echo 0)
                total_size=$((total_size + file_size))
            fi
        done < <(find "$input_dir" -maxdepth 1 -name "*.$ext" -print0 2>/dev/null)
    done
    
    echo "$total_size"
}

# Function to estimate output size based on preset
estimate_output_size() {
    local preset="$1"
    local input_size="$2"
    local quality="$3"
    
    # Convert input size to MB for easier calculation
    local input_mb=$((input_size / 1024 / 1024))
    
    case "$preset" in
        "copy")
            echo "${input_mb}MB (same as input)"
            ;;
        "h264_nvenc"|"h264_qsv"|"h264_vaapi"|"h264_cpu")
            # H.264 typically 20-40% larger than H.265
            local estimated=$((input_mb * 120 / 100))
            echo "${estimated}MB (est. +20%)"
            ;;
        "h265_nvenc"|"h265_qsv"|"h265_vaapi"|"h265_cpu")
            # H.265 typically 20-30% smaller than H.264
            local estimated=$((input_mb * 80 / 100))
            echo "${estimated}MB (est. -20%)"
            ;;
        "av1_nvenc"|"av1_qsv"|"av1_vaapi"|"av1_cpu")
            # AV1 typically 30-50% smaller than H.264
            local estimated=$((input_mb * 60 / 100))
            echo "${estimated}MB (est. -40%)"
            ;;
        "auto")
            # Assume H.265 for auto
            local estimated=$((input_mb * 80 / 100))
            echo "${estimated}MB (est. -20%)"
            ;;
        *)
            echo "${input_mb}MB (unknown)"
            ;;
    esac
}

# Function to encode with NVIDIA NVENC
encode_nvenc() {
    local output="$1"
    local codec="$2"
    local quality="$3"
    shift 3
    local input_files=("$@")
    
    local list_file
    list_file=$(create_file_list "${input_files[@]}")
    
    print_info "Using NVIDIA NVENC ($codec) with quality $quality"
    
    ffmpeg -y \
        -init_hw_device cuda=cuda:0 \
        -filter_hw_device cuda \
        -hwaccel cuda \
        -hwaccel_device 0 \
        -hwaccel_output_format cuda \
        -f concat -safe 0 -i "$list_file" \
        -c:v "$codec" \
        -preset fast \
        -cq "$quality" \
        -c:a copy \
        "$output"
    
    local result=$?
    rm -f "$list_file"
    return $result
}

# Function to encode with Intel QSV
encode_qsv() {
    local output="$1"
    local codec="$2"
    local quality="$3"
    shift 3
    local input_files=("$@")
    
    local list_file
    list_file=$(create_file_list "${input_files[@]}")
    
    print_info "Using Intel QSV ($codec) with quality $quality"
    
    ffmpeg -y \
        -hwaccel qsv \
        -init_hw_device qsv=hw \
        -filter_hw_device hw \
        -f concat -safe 0 -i "$list_file" \
        -c:v "$codec" \
        -preset fast \
        -global_quality "$quality" \
        -c:a copy \
        "$output"
    
    local result=$?
    rm -f "$list_file"
    return $result
}

# Function to encode with VA-API
encode_vaapi() {
    local output="$1"
    local codec="$2"
    local quality="$3"
    shift 3
    local input_files=("$@")
    
    local list_file
    list_file=$(create_file_list "${input_files[@]}")
    
    print_info "Using VA-API ($codec) with quality $quality"
    
    local vaapi_device="${VAAPI_DEVICE:-/dev/dri/renderD128}"
    
    ffmpeg -y \
        -hwaccel vaapi \
        -vaapi_device "$vaapi_device" \
        -f concat -safe 0 -i "$list_file" \
        -c:v "$codec" \
        -qp "$quality" \
        -c:a copy \
        "$output"
    
    local result=$?
    rm -f "$list_file"
    return $result
}

# Function to encode with CPU
encode_cpu() {
    local output="$1"
    local codec="$2"
    local quality="$3"
    shift 3
    local input_files=("$@")
    
    local list_file
    list_file=$(create_file_list "${input_files[@]}")
    
    print_info "Using CPU ($codec) with quality $quality"
    
    ffmpeg -y \
        -f concat -safe 0 -i "$list_file" \
        -c:v "$codec" \
        -preset fast \
        -crf "$quality" \
        -c:a copy \
        "$output"
    
    local result=$?
    rm -f "$list_file"
    return $result
}

# Function to select best encoder
select_encoder() {
    case "$PRESET" in
        "auto")
            if [ "$NVENC_AVAILABLE" = true ]; then
                echo "h265_nvenc"
            elif [ "$QSV_AVAILABLE" = true ]; then
                echo "h265_qsv"
            elif [ "$VAAPI_AVAILABLE" = true ]; then
                echo "h265_vaapi"
            else
                echo "h265_cpu"
            fi
            ;;
        "h264_nvenc"|"h265_nvenc"|"av1_nvenc")
            if [ "$NVENC_AVAILABLE" = true ]; then
                echo "$PRESET"
            else
                print_warning "NVIDIA NVENC not available, falling back to CPU"
                echo "h265_cpu"
            fi
            ;;
        "h264_qsv"|"h265_qsv"|"av1_qsv")
            if [ "$QSV_AVAILABLE" = true ]; then
                echo "$PRESET"
            else
                print_warning "Intel QSV not available, falling back to CPU"
                echo "h265_cpu"
            fi
            ;;
        "h264_vaapi"|"h265_vaapi"|"av1_vaapi")
            if [ "$VAAPI_AVAILABLE" = true ]; then
                echo "$PRESET"
            else
                print_warning "VA-API not available, falling back to CPU"
                echo "h265_cpu"
            fi
            ;;
        "h264_cpu"|"h265_cpu"|"av1_cpu"|"copy")
            echo "$PRESET"
            ;;
        *)
            print_error "Unknown preset: $PRESET"
            exit 1
            ;;
    esac
}

# Function to show usage
show_usage() {
    echo "Usage: $0 <input_directory> [options]"
    echo ""
    echo "Options:"
    echo "  -o, --output FILE     Output file (default: merged_output.mp4)"
    echo "  -p, --preset PRESET   Encoding preset (default: auto)"
    echo "  -q, --quality NUM     Quality setting (default: 25)"
    echo "  -e, --extensions EXT  File extensions (default: mp4 mkv avi)"
    echo "  -l, --list-presets    List available presets with descriptions"
    echo "      --preset-info P   Show detailed info about a preset"
    echo "      --menu            Interactive menu to pick preset and quality"
    echo "  -i, --info           Show system information"
    echo "      --install         Install prerequisites (FFmpeg, codecs, etc.)"
    echo "  -h, --help           Show this help"
    echo ""
    echo "Presets:"
    echo "  auto                 Auto-select best available encoder"
    echo "  h264_nvenc          H.264 NVIDIA NVENC (GPU)"
    echo "  h265_nvenc          H.265 NVIDIA NVENC (GPU)"
    echo "  av1_nvenc           AV1 NVIDIA NVENC (GPU)"
    echo "  h264_qsv            H.264 Intel QSV (GPU)"
    echo "  h265_qsv            H.265 Intel QSV (GPU)"
    echo "  h264_vaapi          H.264 VA-API (GPU)"
    echo "  h265_vaapi          H.265 VA-API (GPU)"
    echo "  h264_cpu            H.264 CPU"
    echo "  h265_cpu            H.265 CPU"
    echo "  av1_cpu             AV1 CPU"
    echo "  copy                Merge only (no re-encoding)"
}

# Function to list presets
# Internal: print a one-line description for a preset
preset_desc_line() {
    local p="$1"
    case "$p" in
        auto)
            echo "Auto-selects best GPU encoder available (prefers H.265/AV1)." ;;
        h264_nvenc)
            echo "GPU H.264: Fast, broad compatibility, larger files than H.265." ;;
        h265_nvenc)
            echo "GPU H.265: Fast, good quality/size balance, widely supported." ;;
        av1_nvenc)
            echo "GPU AV1: Better compression, slower, support varies." ;;
        av1_qsv)
            echo "Intel QSV AV1: Better compression, slower, support varies." ;;
        av1_vaapi)
            echo "VA-API AV1: Better compression, slower, support varies." ;;
        h264_qsv)
            echo "Intel QSV H.264: Fast, compatible, larger files than H.265." ;;
        h265_qsv)
            echo "Intel QSV H.265: Fast, smaller files than H.264, good quality." ;;
        h264_vaapi)
            echo "VA-API H.264: Fast, compatible, larger files." ;;
        h265_vaapi)
            echo "VA-API H.265: Fast, smaller files, good quality." ;;
        h264_cpu)
            echo "CPU H.264: Slow, very compatible, larger files." ;;
        h265_cpu)
            echo "CPU H.265: Slower, smaller files, higher quality at same size." ;;
        av1_cpu)
            echo "CPU AV1: Very slow, smallest files, best quality/bitrate, support varies." ;;
        *) echo "Unknown preset" ;;
    esac
}

# Function to list presets with descriptions
list_presets() {
    echo "Available presets (with trade-offs):"
    echo "  auto        - $(preset_desc_line auto)"
    echo "  h264_nvenc  - $(preset_desc_line h264_nvenc)"
    echo "  h265_nvenc  - $(preset_desc_line h265_nvenc)"
    echo "  av1_nvenc   - $(preset_desc_line av1_nvenc)"
    echo "  h264_qsv    - $(preset_desc_line h264_qsv)"
    echo "  h265_qsv    - $(preset_desc_line h265_qsv)"
    echo "  h264_vaapi  - $(preset_desc_line h264_vaapi)"
    echo "  h265_vaapi  - $(preset_desc_line h265_vaapi)"
    echo "  h264_cpu    - $(preset_desc_line h264_cpu)"
    echo "  h265_cpu    - $(preset_desc_line h265_cpu)"
    echo "  av1_cpu     - $(preset_desc_line av1_cpu)"
    echo
    echo "Tips:"
    echo "- Lower -q QUALITY means higher quality and larger file (GPU cq / CPU crf)."
    echo "- Recommended: -q 18 for near-lossless, -q 22 for good balance, -q 28 for small size."
}

# Function to describe a single preset in detail
describe_preset() {
    local p="$1"
    echo "Preset: $p"
    case "$p" in
        auto)
            echo "- Chooses fastest available GPU encoder (prefers H.265 > H.264; AV1 if supported)."
            echo "- Best for speed and good compression without micromanaging hardware." ;;
        h264_nvenc|h264_qsv|h264_vaapi)
            echo "- Very fast encoding, maximum compatibility (works on most devices/browsers)."
            echo "- Larger files than H.265/AV1 at the same quality."
            echo "- Use when you need broad playback support." ;;
        h265_nvenc|h265_qsv|h265_vaapi)
            echo "- Fast encoding with smaller files than H.264 at similar quality."
            echo "- Widely supported on modern devices; older devices/browsers may need H.264."
            echo "- Great default choice for archiving and general viewing." ;;
        av1_nvenc|av1_qsv|av1_vaapi|av1_cpu)
            echo "- Best compression (smallest files) for a given quality."
            echo "- Slower and playback support is improving but not universal."
            echo "- Choose for long-term storage when size matters most." ;;
        h264_cpu)
            echo "- Slow but very predictable quality; largest files among common choices." ;;
        h265_cpu)
            echo "- Slower than GPU but excellent quality/size; best if no GPU is available." ;;
        *) echo "- Unknown preset" ;;
    esac
}

# Interactive: choose preset via switch-case style menu
choose_preset_menu() {
    print_info "Available presets (only those supported on this system are listed):"

    # Build list of available choices based on detected hardware/encoders
    local choices=("auto")
    if [ "$NVENC_AVAILABLE" = true ]; then
        choices+=("h265_nvenc" "h264_nvenc")
        if encoder_works "av1_nvenc"; then
            choices+=("av1_nvenc")
        fi
    fi
    if [ "$QSV_AVAILABLE" = true ]; then
        choices+=("h265_qsv" "h264_qsv")
        if encoder_works "av1_qsv"; then
            choices+=("av1_qsv")
        fi
    fi
    if [ "$VAAPI_AVAILABLE" = true ]; then
        choices+=("h265_vaapi" "h264_vaapi")
        if encoder_works "av1_vaapi"; then
            choices+=("av1_vaapi")
        fi
    fi
    # Always include CPU fallbacks and a copy-only mode
    choices+=("h265_cpu" "h264_cpu" "av1_cpu" "copy")

    # Calculate input size for estimates
    local input_size=$(calculate_input_size "$INPUT_DIR")
    local input_mb=$((input_size / 1024 / 1024))
    print_info "Input files total: ${input_mb}MB"

    # Print table header with an index column
    printf "\n%-3s %-12s %-6s %-8s %-12s %-50s\n" "#" "PRESET" "HW" "CODEC" "EST. SIZE" "TRADE-OFFS"
    printf "%-3s %-12s %-6s %-8s %-12s %-50s\n" "---" "------------" "------" "--------" "------------" "--------------------------------------------------"

    # Map index -> preset for quick lookup
    declare -a idx_to_preset
    local idx=1
    for p in "${choices[@]}"; do
        local size_est=$(estimate_output_size "$p" "$input_size" "$QUALITY")
        case "$p" in
            auto)
                printf "%-3s %-12s %-6s %-8s %-12s %-50s\n" "$idx" "auto" "AUTO" "auto" "$size_est" "Auto-selects best GPU; fast, good quality/size."
                ;;
            h264_nvenc)
                printf "%-3s %-12s %-6s %-8s %-12s %-50s\n" "$idx" "h264_nvenc" "GPU" "H.264" "$size_est" "Very fast, max compatibility, larger files than H.265."
                ;;
            h265_nvenc)
                printf "%-3s %-12s %-6s %-8s %-12s %-50s\n" "$idx" "h265_nvenc" "GPU" "H.265" "$size_est" "Fast, smaller files than H.264, great default choice."
                ;;
            av1_nvenc)
                printf "%-3s %-12s %-6s %-8s %-12s %-50s\n" "$idx" "av1_nvenc" "GPU" "AV1" "$size_est" "Better compression, slower, support varies."
                ;;
            av1_qsv)
                printf "%-3s %-12s %-6s %-8s %-12s %-50s\n" "$idx" "av1_qsv" "GPU" "AV1" "$size_est" "Better compression, slower, support varies."
                ;;
            av1_vaapi)
                printf "%-3s %-12s %-6s %-8s %-12s %-50s\n" "$idx" "av1_vaapi" "GPU" "AV1" "$size_est" "Better compression, slower, support varies."
                ;;
            h264_qsv)
                printf "%-3s %-12s %-6s %-8s %-12s %-50s\n" "$idx" "h264_qsv" "GPU" "H.264" "$size_est" "Fast, compatible, larger files than H.265."
                ;;
            h265_qsv)
                printf "%-3s %-12s %-6s %-8s %-12s %-50s\n" "$idx" "h265_qsv" "GPU" "H.265" "$size_est" "Fast, good quality/size on Intel iGPU."
                ;;
            h264_vaapi)
                printf "%-3s %-12s %-6s %-8s %-12s %-50s\n" "$idx" "h264_vaapi" "GPU" "H.264" "$size_est" "Fast on VA-API, compatible, larger files."
                ;;
            h265_vaapi)
                printf "%-3s %-12s %-6s %-8s %-12s %-50s\n" "$idx" "h265_vaapi" "GPU" "H.265" "$size_est" "Fast on VA-API, smaller files, good quality."
                ;;
            h264_cpu)
                printf "%-3s %-12s %-6s %-8s %-12s %-50s\n" "$idx" "h264_cpu" "CPU" "H.264" "$size_est" "Slow, very compatible, larger files."
                ;;
            h265_cpu)
                printf "%-3s %-12s %-6s %-8s %-12s %-50s\n" "$idx" "h265_cpu" "CPU" "H.265" "$size_est" "Slower, smaller files, higher quality at same size."
                ;;
            av1_cpu)
                printf "%-3s %-12s %-6s %-8s %-12s %-50s\n" "$idx" "av1_cpu" "CPU" "AV1" "$size_est" "Very slow, smallest files, best quality/bitrate."
                ;;
            copy)
                printf "%-3s %-12s %-6s %-8s %-12s %-50s\n" "$idx" "copy" "N/A" "Stream" "$size_est" "Merge-only: no re-encode, fastest, identical quality."
                ;;
        esac
        idx_to_preset[$idx]="$p"
        idx=$((idx+1))
    done

    echo
    print_info "Enter a number to select, or 'i <number>' for details, or 'q' to quit."
    while true; do
        read -rp "> " answer
        case "$answer" in
            q|Q|quit|exit) exit 0 ;;
            i\ *|I\ *)
                num=${answer#* }
                if [[ "$num" =~ ^[0-9]+$ ]] && [ -n "${idx_to_preset[$num]}" ]; then
                    echo
                    describe_preset "${idx_to_preset[$num]}"
                    echo
                else
                    echo "Invalid number for details."
                fi
                ;;
            *)
                if [[ "$answer" =~ ^[0-9]+$ ]] && [ -n "${idx_to_preset[$answer]}" ]; then
                    PRESET="${idx_to_preset[$answer]}"
                    print_success "Selected preset: $PRESET"
                    break
                else
                    echo "Invalid selection."
                fi
                ;;
        esac
    done
}

# Interactive: choose quality via menu
choose_quality_menu() {
    print_info "Select quality (lower is higher quality, larger size):"
    echo "1) Near-lossless (18)"
    echo "2) Balanced (22)"
    echo "3) Smaller (28)"
    echo "4) Custom"
    local choice
    read -rp "> " choice
    case "$choice" in
        1) QUALITY=18 ;;
        2) QUALITY=22 ;;
        3) QUALITY=28 ;;
        4)
            read -rp "Enter numeric quality (e.g., 18..32): " q
            QUALITY="$q"
            ;;
        *) echo "Using default quality: $QUALITY" ;;
    esac
    print_success "Selected quality: $QUALITY"
}

# Function to detect most common input file extension
detect_common_extension() {
    local input_dir="$1"
    local files=()
    
    # Find all video files
    for ext in $EXTENSIONS; do
        while IFS= read -r -d '' file; do
            files+=("$file")
        done < <(find "$input_dir" -maxdepth 1 -name "*.$ext" -print0 2>/dev/null)
    done
    
    if [ ${#files[@]} -eq 0 ]; then
        echo "mp4"  # fallback
        return
    fi
    
    # Count extensions
    declare -A ext_count
    for file in "${files[@]}"; do
        ext="${file##*.}"
        ext="${ext,,}"  # convert to lowercase
        ((ext_count[$ext]++))
    done
    
    # Find most common extension
    local most_common="mp4"
    local max_count=0
    for ext in "${!ext_count[@]}"; do
        if [ ${ext_count[$ext]} -gt $max_count ]; then
            max_count=${ext_count[$ext]}
            most_common="$ext"
        fi
    done
    
    echo "$most_common"
}

# Interactive: prompt for output filename with path selection
choose_output_menu() {
    # Auto-generate output name based on input folder and common extension
    local folder_name=$(basename "$INPUT_DIR")
    local common_ext=$(detect_common_extension "$INPUT_DIR")
    local suggested_name="${folder_name}_merged.${common_ext}"
    local suggested_path="$(pwd)/${suggested_name}"
    
    print_info "Output file: $suggested_path (using most common input extension: .${common_ext})"
    print_info "Do you want to change the output filename and/or location? (y/n)"
    read -rp "> " change_output
    
    case "$change_output" in
        y|Y|yes|YES)
            print_info "Enter new output path (with filename and extension):"
            print_info "  - Use tab completion for directories"
            print_info "  - Include filename and extension (e.g., /path/to/video.mp4)"
            print_info "  - Press Enter to use suggested path"
            
            # Enable tab completion for readline
            if command -v readline >/dev/null 2>&1; then
                # Use readline with tab completion
                read -e -rp "> " new_output
            else
                # Fallback to regular read
                read -rp "> " new_output
            fi
            
            if [ -n "$new_output" ]; then
                # Expand tilde and relative paths
                new_output=$(eval echo "$new_output")
                
                # If it's just a filename without path, use current directory
                if [[ "$new_output" != */* ]]; then
                    new_output="$(pwd)/$new_output"
                fi
                
                # Create directory if it doesn't exist
                local output_dir=$(dirname "$new_output")
                if [ ! -d "$output_dir" ]; then
                    print_info "Creating directory: $output_dir"
                    mkdir -p "$output_dir" 2>/dev/null || {
                        print_error "Failed to create directory: $output_dir"
                        print_warning "Using suggested path instead: $suggested_path"
                        OUTPUT_FILE="$suggested_path"
                        return
                    }
                fi
                
                OUTPUT_FILE="$new_output"
                print_success "Output file set to: $OUTPUT_FILE"
            else
                OUTPUT_FILE="$suggested_path"
                print_warning "Empty input, using suggested path: $OUTPUT_FILE"
            fi
            ;;
        *)
            OUTPUT_FILE="$suggested_path"
            print_success "Using suggested output file: $OUTPUT_FILE"
            ;;
    esac
}

# Function to show system info
show_info() {
    print_info "System Information:"
    echo "FFmpeg: $(ffmpeg -version | head -1)"
    echo "CPU cores: $(nproc)"
    echo "Platform: $(uname -s)"
    
    if command_exists nvidia-smi; then
        echo "NVIDIA GPU:"
        nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits 2>/dev/null || echo "  No NVIDIA GPU detected"
    fi
    
    echo ""
    print_info "Hardware acceleration:"
    detect_hardware
}

# Main encoding function
encode_videos() {
    local input_dir="$1"
    local output_file="$2"
    local selected_preset="$3"
    local quality="$4"
    
    # Find video files
    print_info "Scanning directory: $input_dir"
    mapfile -t video_files < <(find_video_files "$input_dir")
    
    if [ ${#video_files[@]} -eq 0 ]; then
        print_error "No video files found in $input_dir"
        exit 1
    fi
    
    print_success "Found ${#video_files[@]} video files:"
    for i in "${!video_files[@]}"; do
        local info
        info=$(get_video_info "${video_files[i]}")
        echo "  $((i+1)). $(basename "${video_files[i]}") - $info"
    done
    
    # Select encoder
    local encoder
    encoder=$(select_encoder)
    
    print_info "Selected encoder: $encoder"
    
    # Encode based on selected encoder
    case "$encoder" in
        "copy")
            # Merge without re-encoding
            local list_file
            list_file=$(create_file_list "${video_files[@]}")
            print_info "Merging without re-encoding (stream copy)"
            ffmpeg -y -f concat -safe 0 -i "$list_file" -c copy "$output_file"
            local result=$?
            rm -f "$list_file"
            return $result
            ;;
        "h264_nvenc")
            encode_nvenc "$output_file" "h264_nvenc" "$quality" "${video_files[@]}"
            ;;
        "h265_nvenc")
            encode_nvenc "$output_file" "hevc_nvenc" "$quality" "${video_files[@]}"
            ;;
        "av1_nvenc")
            encode_nvenc "$output_file" "av1_nvenc" "$quality" "${video_files[@]}"
            ;;
        "h264_qsv")
            encode_qsv "$output_file" "h264_qsv" "$quality" "${video_files[@]}"
            ;;
        "h265_qsv")
            encode_qsv "$output_file" "hevc_qsv" "$quality" "${video_files[@]}"
            ;;
        "av1_qsv")
            encode_qsv "$output_file" "av1_qsv" "$quality" "${video_files[@]}"
            ;;
        "h264_vaapi")
            encode_vaapi "$output_file" "h264_vaapi" "$quality" "${video_files[@]}"
            ;;
        "h265_vaapi")
            encode_vaapi "$output_file" "hevc_vaapi" "$quality" "${video_files[@]}"
            ;;
        "av1_vaapi")
            encode_vaapi "$output_file" "av1_vaapi" "$quality" "${video_files[@]}"
            ;;
        "h264_cpu")
            encode_cpu "$output_file" "libx264" "$quality" "${video_files[@]}"
            ;;
        "h265_cpu")
            encode_cpu "$output_file" "libx265" "$quality" "${video_files[@]}"
            ;;
        "av1_cpu")
            encode_cpu "$output_file" "libaom-av1" "$quality" "${video_files[@]}"
            ;;
        *)
            print_error "Unknown encoder: $encoder"
            exit 1
            ;;
    esac
    
    if [ $? -eq 0 ]; then
        print_success "Successfully created: $output_file"
        local file_size
        file_size=$(du -h "$output_file" | cut -f1)
        echo "File size: $file_size"
    else
        print_error "Encoding failed"
        exit 1
    fi
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -o|--output)
            OUTPUT_FILE="$2"
            shift 2
            ;;
        -p|--preset)
            PRESET="$2"
            shift 2
            ;;
        -q|--quality)
            QUALITY="$2"
            shift 2
            ;;
        -e|--extensions)
            EXTENSIONS="$2"
            shift 2
            ;;
        -l|--list-presets)
            list_presets
            exit 0
            ;;
        --preset-info)
            describe_preset "$2"
            exit 0
            ;;
        --menu)
            MENU=true
            shift
            ;;
        -i|--info)
            show_info
            exit 0
            ;;
        --install)
            install_prerequisites
            exit 0
            ;;
        -h|--help)
            show_usage
            exit 0
            ;;
        -*)
            print_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
        *)
            if [ -z "$INPUT_DIR" ]; then
                INPUT_DIR="$1"
            else
                print_error "Multiple input directories specified"
                exit 1
            fi
            shift
            ;;
    esac
done

# Check if input directory is provided
if [ -z "$INPUT_DIR" ]; then
    print_error "Input directory is required"
    show_usage
    exit 1
fi

# Check if input directory exists
if [ ! -d "$INPUT_DIR" ]; then
    print_error "Directory not found: $INPUT_DIR"
    exit 1
fi

# Detect hardware
detect_hardware

# Auto-generate output filename if not specified
if [ "$OUTPUT_FILE" = "merged_output.mp4" ]; then
    folder_name=$(basename "$INPUT_DIR")
    common_ext=$(detect_common_extension "$INPUT_DIR")
    OUTPUT_FILE="${folder_name}_merged.${common_ext}"
    print_info "Auto-generated output: $OUTPUT_FILE (using most common input extension: .${common_ext})"
fi

# If interactive menu requested, prompt for choices
if [ "$MENU" = true ]; then
    choose_preset_menu
    choose_quality_menu
    choose_output_menu
fi

# Encode videos
encode_videos "$INPUT_DIR" "$OUTPUT_FILE" "$PRESET" "$QUALITY"
