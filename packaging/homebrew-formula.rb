class Pdf2xlsx < Formula
  desc "PDF to XLSX table extractor with GUI and CLI"
  homepage "https://github.com/h4x0r/pdf2xlsx"
  version "0.1.0"

  on_macos do
    if Hardware::CPU.arm?
      url "https://github.com/h4x0r/pdf2xlsx/releases/download/v#{version}/pdf2xlsx-aarch64-apple-darwin.tar.gz"
      sha256 "PLACEHOLDER_ARM64_MAC"
    else
      url "https://github.com/h4x0r/pdf2xlsx/releases/download/v#{version}/pdf2xlsx-x86_64-apple-darwin.tar.gz"
      sha256 "PLACEHOLDER_X86_64_MAC"
    end
  end

  on_linux do
    if Hardware::CPU.arm?
      url "https://github.com/h4x0r/pdf2xlsx/releases/download/v#{version}/pdf2xlsx-aarch64-unknown-linux-musl.tar.gz"
      sha256 "PLACEHOLDER_ARM64_LINUX"
    else
      url "https://github.com/h4x0r/pdf2xlsx/releases/download/v#{version}/pdf2xlsx-x86_64-unknown-linux-musl.tar.gz"
      sha256 "PLACEHOLDER_X86_64_LINUX"
    end
  end

  def install
    bin.install "pdf2xlsx"
    bin.install "pdf2xlsx-gui" if File.exist?("pdf2xlsx-gui")
  end

  test do
    system "#{bin}/pdf2xlsx", "--help"
  end
end
